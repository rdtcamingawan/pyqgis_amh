import sys, os
import logging

# ← MUST be first, before geopandas/fiona/rasterio/etc.
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    os.environ['GDAL_DATA'] = os.path.join(base, 'gdal-data')
    os.environ['PROJ_LIB']  = os.path.join(base, 'proj-data')
    from osgeo import gdal, ogr
    gdal.AllRegister()
    ogr.RegisterAll()

import fiona
import geopandas as gpd
import rasterio
from rasterio.warp      import calculate_default_transform, reproject, Resampling
from rasterio.features  import rasterize
from rasterio.warp      import transform_geom
from shapely.geometry   import LineString, mapping
import h5py
import numpy as np
import pandas as pd
import re
from glob               import glob

import tkinter as tk
from tkinter import filedialog, ttk, messagebox


# intialize a logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

class ExtractFlowApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Extract Flow")

        # ——— State ———
        self.selected_folder = None
        self.selected_ref_lineshp_file = None
        self.selected_terrain_file = None
        self.selected_field = None

        # ——— UI ———
        # RAS Folder
        frame = tk.Frame(self); frame.pack(fill="x", padx=10, pady=5)
        self.folder_label = tk.Label(frame, text="Select RAS Folder:")
        self.folder_label.pack(side="left")
        tk.Button(frame, text="...", width=3, command=self.select_ras_folder)\
          .pack(side="left", padx=(5,0))
        
        # Terrain
        frame = tk.Frame(self); frame.pack(fill="x", padx=10, pady=5)
        self.terrain_label = tk.Label(frame, text="Select Terrain:")
        self.terrain_label.pack(side="left")
        tk.Button(frame, text="...", width=3, command=self.select_terrain_file)\
          .pack(side="left", padx=(5,0))

        # Profile Line
        frame = tk.Frame(self); frame.pack(fill="x", padx=10, pady=5)
        self.ref_label = tk.Label(frame, text="Select Profile Line:")
        self.ref_label.pack(side="left")
        tk.Button(frame, text="...", width=3, command=self.select_ref_lineshp_file)\
          .pack(side="left", padx=(5,0))
        
        # Combobox
        frame = tk.Frame(self); frame.pack(fill="x", padx=10, pady=5)
        tk.Label(frame, text="Select Field Column:").pack(side="left")
        self.combobox = ttk.Combobox(frame, state="readonly")
        self.combobox.pack(side="left", fill="x", expand=True, padx=(5,0))
        self.combobox.bind("<<ComboboxSelected>>", self.on_combobox_change)      

        # Compute & Progress
        self.compute_button = tk.Button(self, text="Compute", command=self.output_flow)
        self.compute_button.pack(pady=(10,0))
        self.progress_bar = ttk.Progressbar(self, orient="horizontal",
                                            length=300, mode="determinate")
        self.progress_bar.pack_forget()

        # Exit
        self.exit_button = tk.Button(self, text="Exit", command=self.exit_app)
        self.exit_button.pack(pady=(5,10))


    # ——— File dialogs ———
    def select_ras_folder(self):
        folder = filedialog.askdirectory(title="Select RAS Folder")
        if not folder:
            return

        self.selected_folder = folder
        self.folder_label.config(text=f"Selected RAS Folder: {folder}")

        # — configure logging into that folder —
        log_path = os.path.join(folder, 'log_file.txt')

        # remove any old FileHandlers so we don't double‐log
        for h in list(logger.handlers):
            if isinstance(h, logging.FileHandler):
                logger.removeHandler(h)

        # add a new FileHandler
        fh = logging.FileHandler(log_path, mode='a')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        logger.addHandler(fh)
        logger.info("Logging initialized in %s", log_path)


    def select_ref_lineshp_file(self):
        shp = filedialog.askopenfilename(
            title="Select Profile Line",
            filetypes=[("Shapefiles", "*.shp")]
        )
        if not shp:
            return

        self.selected_ref_lineshp_file = shp
        self.ref_label.config(text=os.path.basename(shp))

        # load & cache GDF in both CRS’s
        self._gdf_orig  = gpd.read_file(shp)
        self._gdf_32651 = self._gdf_orig.to_crs(epsg=32651)

        # populate combobox from the in-memory GDF
        fields = list(self._gdf_orig.columns)
        self.combobox['values'] = fields
        if fields:
            self.combobox.current(0)
            self.selected_field = fields[0]

    def select_terrain_file(self):
        raster = filedialog.askopenfilename(
            title="Select Terrain",
            filetypes=[("Rasters", "*.vrt *.tiff *.tif")]
        )
        if raster:
            self.selected_terrain_file = raster
            self.terrain_label.config(text=os.path.basename(raster))

    # ——— Combobox ———
    def populate_combobox(self):
        fields = list(self._gdf_orig.columns)
        self.combobox['values'] = fields
        if fields:
            self.combobox.current(0)
            self.selected_field = fields[0]

    def on_combobox_change(self, event):
        self.selected_field = self.combobox.get()

    # ——— Helper Function to Sample along line ———
    def _sample_along_line(self, raster_path, line, reducer, default=0.0):
        """
        Open `raster_path`, rasterize the `line` into it, then return
        reducer(masked_array). On any error, return `default`.
        `reducer` is a function like np.nanmin or np.nanmax.
        """
        try:
            with rasterio.open(raster_path) as src:
                # reproject your line into the raster’s CRS
                geom = transform_geom('EPSG:32651', src.crs, mapping(line))
                mask = rasterize(
                    [(geom, 1)],
                    out_shape=(src.height, src.width),
                    transform=src.transform
                )
                data = src.read(1)
                arr = np.where(mask == 1, data, np.nan)
                return float(reducer(arr))
        except Exception:
            logger.exception("Error sampling raster %s for line %s", raster_path, line)
            return default
        
    # ——— Flow Extraction ———
    def get_values(self, station, plan_shortID):
        """
        Returns (min_terrain, max_velocity, max_froude) along the reference line.
        If the corresponding VRTs are missing, velocity or froude will be 0.
        """
        plan_folder = os.path.join(self.selected_folder, plan_shortID)
        row = self._gdf_32651[self._gdf_orig[self.selected_field] == station]
        # ——— Load & reproject the line geometry ———
        # gdf = gpd.read_file(self.selected_ref_lineshp_file).to_crs(epsg=32651)
        
        if row.empty:
            raise ValueError(f"Station {station!r} not found in shapefile.")
        line = row.geometry.iloc[0]

        # ——— Terrain (always expected) ———
        terrain_raster = self.selected_terrain_file
        min_terrain = self._sample_along_line(
            terrain_raster, line, reducer=np.nanmin, default=np.nan
                                )

        # ——— Max Velocity ———
        vel_paths = glob(os.path.join(plan_folder, 'Velocity (Max).vrt'))
        max_velocity = (
            self._sample_along_line(vel_paths[0], line, reducer=np.nanmax)
            if vel_paths else 0.0
            )   

        # ——— Max Froude ———
        fr_paths  = glob(os.path.join(plan_folder, 'Froude (Max).vrt'))
        max_froude = (
            self._sample_along_line(fr_paths[0], line, reducer=np.nanmax)
            if fr_paths else 0.0
        )

        return min_terrain, max_velocity, max_froude


    def flow_extract(self, plan_file):
        """
        Read just the discharge and water‐surface series from the HDF
        and return a small DataFrame of per‐station maxima.
        If the Reference Lines path is missing, returns None.
        """
        try:
            with h5py.File(plan_file, 'r') as f:
                # 1) make sure the Reference Lines Attributes path exists
                ref_attr_path = '/Geometry/Reference Lines/Attributes'
                if ref_attr_path not in f:
                    # no reference lines → skip
                    raise KeyError(f"Missing HDF group {ref_attr_path!r}")

                # pull out plan metadata
                info = f['/Plan Data/Plan Information']
                plan_shortID = info.attrs['Plan ShortID'].decode('utf-8')
                flow_id     = info.attrs['Flow Title'].decode('utf-8')

                # reference line station names
                attrs = np.array(f[ref_attr_path])
                stations = [x[0].decode('utf-8') for x in attrs]

                # max discharge per station
                ts = np.abs(f[
                  '/Results/Unsteady/Output/Output Blocks/'
                  'DSS Hydrograph Output/Unsteady Time Series/Reference Lines/Flow'
                ])
                max_discharge = np.max(ts, axis=0).tolist()

                # max WSE per station
                wse_ts = f[
                  '/Results/Unsteady/Output/Output Blocks/'
                  'DSS Hydrograph Output/Unsteady Time Series/Reference Lines/Water Surface'
                ]
                max_wse = np.max(wse_ts, axis=0).tolist()

        except (KeyError, OSError) as e:
            logger.warning("Skipping %s: %s", os.path.basename(plan_file), e)
            return None

        # build and return DataFrame if everything succeeded
        return pd.DataFrame({
            'Plan ShortID':   plan_shortID,
            'Station':        stations,
            'Flow Scenario':  flow_id,
            'Discharge':      max_discharge,
            'WSE':            max_wse
        })


    def output_flow(self):
        # hide button, show progress
        self.compute_button.pack_forget()
        self.progress_bar.pack()
        self.progress_bar['value'] = 0
        self.update_idletasks()

        if not self.selected_folder:
            messagebox.showwarning("No Folder", "Please select a RAS folder first.")
            self.progress_bar.pack_forget()
            self.compute_button.pack()
            return

        # — Ask user where/how to save —
        save_csv = filedialog.asksaveasfilename(
            title="Save summary CSV as…",
            initialdir=self.selected_folder,
            defaultextension=".csv",
            filetypes=[("CSV files","*.csv")]
        )
        if not save_csv:
            # user cancelled
            self.progress_bar.pack_forget()
            self.compute_button.pack()
            return
        save_html = os.path.splitext(save_csv)[0] + ".html"

        self.progress_bar['value'] = 5
        self.update_idletasks()

        # gather plans
        plans = glob(os.path.join(self.selected_folder, '*.p*.hdf'))
        total_plans = len(plans)
        dfs = []
        skip_records = []

        for plan in plans:
            # 1) get the ShortID (for logging)
            try:
                with h5py.File(plan, 'r') as f:
                    plan_shortID = f[
                        '/Plan Data/Plan Information'
                    ].attrs['Plan ShortID'].decode('utf-8')
            except Exception:
                logger.exception("Error reading Plan ShortID from %s", plan)
                plan_shortID = 'Unknown'

            # 2) attempt to extract
            df = self.flow_extract(plan)
            if df is None:
                skip_records.append((plan_shortID, os.path.basename(plan)))
                continue
            dfs.append(df)

            # advance progress bar a bit per plan
            self.progress_bar['value'] += int(50/total_plans)
            self.update_idletasks()

        processed = len(dfs)
        skipped   = len(skip_records)

        if not dfs:
            messagebox.showinfo(
                "Nothing to do",
                "No valid HDF files found with Reference Lines."
            )
            self.progress_bar.pack_forget()
            self.compute_button.pack()
            return

        # — concat & compute as before —
        df_all = pd.concat(dfs, ignore_index=True)
        uniq = (df_all[['Plan ShortID','Station']]
                .drop_duplicates()
                .reset_index(drop=True))

        metrics = uniq.apply(
            lambda r: pd.Series(
                self.get_values(r['Station'], r['Plan ShortID']),
                index=['Thalweg','MaxVelocity','MaxFroude']
            ),
            axis=1
        )
        metrics_df = pd.concat([uniq, metrics], axis=1)
        df_merged = df_all.merge(metrics_df,
                                on=['Plan ShortID','Station'],
                                how='left')

        # Flow Area (guard div-by-zero)
        df_merged['Flow Area'] = df_merged.apply(
            lambda r: r['Discharge']/r['MaxVelocity']
                    if r['MaxVelocity']>0 else 0.0,
            axis=1
        )
        # EGL
        g = 9.81
        df_merged['EGL'] = df_merged['WSE'] + df_merged['MaxVelocity']**2/(2*g)

        # round, sort, save
        floats = df_merged.select_dtypes('float').columns
        df_merged[floats] = df_merged[floats].round(3)
        df_merged.sort_values(
            by=['Station','Flow Scenario'],
            key=lambda col: col.map(self.station_sort_key),
            inplace=True
        )

        df_merged.to_csv(save_csv, index=False)
        df_merged.to_html(save_html, index=False)

        # finish UI
        self.progress_bar['value'] = 100
        self.update_idletasks()
        self.progress_bar.pack_forget()
        self.compute_button.pack()

        # — Final summary with skipped details —
        summary = (f"Processed {processed} of {total_plans} plans "
                f"(skipped {skipped}).\n\n")
        if skip_records:
            summary += "Skipped Plans (ShortID – file):\n"
            summary += "\n".join(f"• {pid}  –  {fname}"
                                for pid, fname in skip_records)

        messagebox.showinfo("Done!", summary)

    def station_sort_key(self, station_str):
        m = re.match(r'Station-(\d+)(?:\+(\d+))?', station_str)
        if m:
            base = int(m.group(1))
            offset = int(m.group(2)) if m.group(2) else 0
            return (base, offset)
        return (float('inf'), 0)

    # ——— Exit ———
    def exit_app(self):
        # properly destroy the window and end mainloop
        self.destroy()

if __name__ == "__main__":
    app = ExtractFlowApp()
    app.mainloop()
