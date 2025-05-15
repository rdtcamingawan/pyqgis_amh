###############################################################################
#  Amacan HMS helper with Tkinter front‑end
###############################################################################
import os, sys, io, threading, datetime
import numpy as np
import pandas as pd
from tkinter import Tk, filedialog, ttk, StringVar, scrolledtext, END, VERTICAL, HORIZONTAL
from pydsstools.heclib.dss import HecDss
from matplotlib import pyplot as plt
import matplotlib.dates as mdates
# Set a date format
dtFmt = mdates.DateFormatter('%dd-%b') # 01-Jan
# If you prefer an embedded plot inside Tkinter, uncomment the next 2 lines
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# plt.switch_backend("Agg")        # keep tk backend free for embedding

# ───────────────────────────────  FUNCTIONS  ─────────────────────────────── #

def parse_subbasin_reach(filepath):
    """Parses *.basin file into DataFrame (unchanged logic)."""
    records, current, in_code = [], None, False
    with open(filepath, "r") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith(("Subbasin:", "Reach:")):
                if current: records.append(current)
                kind, name = line.split(":", 1)
                current, in_code = {"type": kind, "name": name.strip()}, False
                continue
            if line == "```":                       # toggle code block
                in_code = not in_code;  continue
            if line == "End:":
                if current: records.append(current)
                current, in_code = None, False
                continue
            if ":" in line and current is not None:
                k, v = line.split(":", 1)
                col = k.strip().lower().replace(" ", "_").replace("-", "_")
                current[col] = v.strip()
    df = pd.DataFrame(records)
    expected_cols = [  # same fixed order as your script
        'type','name','area','downstream','discretization','canopy',
        'allow_simultaneous_precip_et','plant_uptake_method',
        'initial_canopy_storage_percent','canopy_storage_capacity',
        'crop_coefficient','surface','initial_surface_storage_percent',
        'surface_storage_capacity','surface_albedo','lossrate',
        'percent_impervious_area','initial_soil_storage_percent',
        'initial_gw1_storage_percent','initial_gw2_storage_percent',
        'soil_maximum_infiltration','soil_storage_capacity',
        'soil_tension_capacity','soil_maximum_percolation',
        'groundwater_1_storage_capacity','groundwater_1_routing_coefficient',
        'groundwater_1_maximum_percolation','groundwater_2_storage_capacity',
        'groundwater_2_routing_coefficient','groundwater_2_maximum_percolation',
        'transform','lag','unitgraph_type','baseflow','recession_factor',
        'initial_baseflow','threshold_flow_to_peak_ratio','route',
        'initial_variable','channel_loss']
    # make sure all columns exist even if blank
    for c in expected_cols:
        if c not in df.columns: df[c] = np.nan
    return df[expected_cols]

def save_with_sequential_run_id(df, master_csv):
    """Append df to CSV and tag with Run N."""
    if not os.path.exists(os.path.dirname(master_csv)):
        os.makedirs(os.path.dirname(master_csv))
    if os.path.exists(master_csv):
        nums = pd.read_csv(master_csv, usecols=["run_id"])["run_id"] \
                .str.extract(r"Run\s+(\d+)", expand=False) \
                .astype(float).dropna()
        next_run = int(nums.max()) + 1 if not nums.empty else 1
    else:
        next_run = 1
    run_id = f"Run {next_run}"
    df = df.copy();  df["run_id"] = run_id
    df.to_csv(master_csv, mode="a", index=False, header=not os.path.exists(master_csv))
    return run_id

def compute_nse_per_run(df, run_id, hms_dss_path, dss_name, csv_save_path):
    mapping = {
        'Bunlang EP'        : ['Bunlang Catchment 1', 'Bunlang Catchment 2'],
        'Masara EP'         : ['Masara Catchment'],
        'Simsimin Catchment': ['Simsimin Catchment']
    }
    extraction_points = ['Bunlang EP', 'Masara EP', 'Simsimin Catchment']
    subbasins         = ['Bunlang Creek', 'Masara River', 'Simsimin Creek']

    with HecDss.Open(hms_dss_path) as dss:
        for ep, sub in zip(extraction_points, subbasins):
            dss_path = f"//{ep}/FLOW/01Jan2025/1Day/RUN:{dss_name}/"
            ts = dss.read_ts(dss_path,
                             window=('02Feb2025 00:00:00','08Apr2025 00:00:00'),
                             trim_missing=True)
            df_ts = pd.DataFrame({'date': np.array(ts.pytimes),
                                  'pred_value': ts.values})

            allowed = pd.to_datetime([
                "03/02/2025","07/02/2025","10/02/2025","12/02/2025","14/02/2025",
                "17/02/2025","19/02/2025","03/03/2025","05/03/2025","07/03/2025",
                "12/03/2025","17/03/2025","24/03/2025","26/03/2025","28/03/2025",
                "31/03/2025","02/04/2025","07/04/2025"], dayfirst=True)

            df_sim = df_ts[df_ts['date'].isin(allowed)].reset_index(drop=True)
            df_obs_f = df_obs[df_obs['extraction_point'] == sub]
            df_m = pd.merge(df_obs_f, df_sim, on='date')
            mean_obs = df_m['discharge'].mean()
            nse = 1 - (((df_m['discharge']-df_m['pred_value'])**2).sum() / \
                        ((df_m['discharge']-mean_obs)**2).sum())
            print(f"NSE for {ep:>15}: {nse:8.4f}")

            mask = (df['run_id']==run_id) & (df['name'].isin(mapping[ep]))
            df.loc[mask,'nse'] = nse
            # print(f"Assigned NSE {nse:8.4f} → {mapping[ep]}")
    df.to_csv(csv_save_path, index=False)

def plot_current_run(hms_dss_path, dss_name, csv_save_path):
    df = pd.read_csv(csv_save_path)

    mapping = {
        'Bunlang EP'        : ['Bunlang Catchment 1', 'Bunlang Catchment 2'],
        'Masara EP'         : ['Masara Catchment'],
        'Simsimin Catchment': ['Simsimin Catchment']
    }
    extraction_points = ['Bunlang EP','Masara EP','Simsimin Catchment']
    subbasins         = ['Bunlang Creek','Masara River','Simsimin Creek']

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()

    with HecDss.Open(hms_dss_path) as dss:
        for i, (ep, sub) in enumerate(zip(extraction_points, subbasins)):
            ax = axes[i]
            dss_path = f"//{ep}/FLOW/01Jan2025/1Day/RUN:{dss_name}/"
            ts = dss.read_ts(dss_path,
                             window=('02Feb2025 00:00:00', '08Apr2025 00:00:00'),
                             trim_missing=True)
            df_ts = pd.DataFrame({'date': np.array(ts.pytimes),
                                  'pred_value': ts.values})
            allowed = pd.to_datetime([
                "03/02/2025","07/02/2025","10/02/2025","12/02/2025","14/02/2025",
                "17/02/2025","19/02/2025","03/03/2025","05/03/2025","07/03/2025",
                "12/03/2025","17/03/2025","24/03/2025","26/03/2025","28/03/2025",
                "31/03/2025","02/04/2025","07/04/2025"], dayfirst=True)
            df_sim  = df_ts[df_ts['date'].isin(allowed)].reset_index(drop=True)
            df_obs_f = df_obs[df_obs['extraction_point'] == sub]
            df_m = pd.merge(df_obs_f, df_sim, on='date').set_index('date')

            # ── plotting ───────────────────────────────────────────────────
            ax.scatter(df_m.index, df_m['discharge'],
                       marker='o', color='r', label=f'Obs {sub}')
            ax.plot(df_m.index, df_m['pred_value'], '-+',
                    label=f'Sim {sub}')
            ax.set_title(sub)
            ax.set_xlabel('Date'); ax.set_ylabel('Discharge')
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
        

    # NSE subplot bottom‑right
    ax = axes[3]
    ax.set_title('NSE per extraction point')
    for ep in extraction_points:
        nse_vals = df[df['name'].isin(mapping[ep])]['nse']
        ax.plot(nse_vals.values, label=f'NSE {ep}')
    ax.legend()

    # fig.autofmt_xdate()
    fig.tight_layout()

    return fig       


# ────────────────────────────  TKINTER GUI  ──────────────────────────────── #

class RedirectToText:
    """File‑like object to redirect stdout to a Tkinter ScrolledText."""
    def __init__(self, text_widget): self.text = text_widget
    def write(self, s):
        self.text.insert(END, s); self.text.see(END)
    def flush(self): pass   

def run_model():
    """Collect user inputs, run the whole pipeline in a worker thread."""
    # Gather parameters
    project_dir = project_dir_var.get()
    basin_name  = basin_var.get() or "EDC_Basin"
    dss_name    = dss_var.get()   or "edc_run_v1"
    xl_path     = xl_var.get()

    if not (project_dir and basin_name and dss_name and xl_path):
        print("Please fill in every field."); return

    # Build derived paths
    basin_path  = os.path.join(project_dir, f"{basin_name}.basin")
    dss_path    = os.path.join(project_dir, f"{dss_name}.dss")
    csv_path    = os.path.join(project_dir, 'NSE_computation', 'NSE.csv')

    # print("\n────────────  RUN STARTED", datetime.datetime.now().strftime("%c"), "────────────")
    # print(f"HMS Project Dir  : {project_dir}")
    # print(f"Basin file       : {os.path.basename(basin_path)}")
    # print(f"DSS file         : {os.path.basename(dss_path)}")
    # print(f"Observed data    : {os.path.basename(xl_path)}")
    # print("────────────────────────────────────────────────────────────────────────")

    # bring df_obs into global scope for downstream functions
    global df_obs
    df_obs = pd.read_excel(xl_path)

    # main pipeline
    df = parse_subbasin_reach(basin_path)
    run_id = save_with_sequential_run_id(df, csv_path)
    df = pd.read_csv(csv_path)
    compute_nse_per_run(df, run_id, dss_path, dss_name, csv_path)
    plot_current_run(dss_path, dss_name, csv_path)

    fig = plot_current_run(dss_path, dss_name, csv_path)

    # ---- embed or refresh canvas --------------------------------------------
    global plot_canvas        
    try:
        plot_canvas.get_tk_widget().destroy()
    except NameError:
        pass                    

    plot_canvas = FigureCanvasTkAgg(fig, master=root)  
    plot_canvas.draw()
    plot_canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=5)

    print("────────────  RUN FINISHED  ───────────────────────────────────────────")

def start_thread():
    """Run model in a background thread so the GUI stays responsive."""
    threading.Thread(target=run_model, daemon=True).start()

root = Tk();  root.title("Amacan HMS NSE helper")

# ---------- input frame ----------
frm = ttk.Frame(root, padding=10); frm.pack(fill='x')
def add_row(label, textvariable, browse_cmd=None):
    row = ttk.Frame(frm); row.pack(fill='x', pady=2)
    ttk.Label(row, text=label, width=15).pack(side='left')
    e = ttk.Entry(row, textvariable=textvariable); e.pack(side='left', fill='x', expand=True)
    if browse_cmd:
        ttk.Button(row, text="…", width=3, command=browse_cmd).pack(side='left')
project_dir_var = StringVar()
basin_var       = StringVar(value="EDC_Basin")
dss_var         = StringVar(value="edc_run_v1")
xl_var          = StringVar()

add_row("Project dir:", project_dir_var,
        lambda: project_dir_var.set(filedialog.askdirectory()))
add_row("Basin name :", basin_var)
add_row("DSS name   :", dss_var)
add_row("Observed xlsx:", xl_var,
        lambda: xl_var.set(filedialog.askopenfilename(
            filetypes=[("Excel files","*.xlsx"),("All files","*")] )))
ttk.Button(frm, text="Run model", command=start_thread).pack(pady=1)

# ---------- log / output frame ----------
log = scrolledtext.ScrolledText(root, height=10, wrap='word')
log.pack(fill='both', expand=False, padx=10, pady=(0,3))

# Redirect stdout so every print appears in the GUI
sys.stdout = RedirectToText(log)
sys.stderr = RedirectToText(log)

root.mainloop()
