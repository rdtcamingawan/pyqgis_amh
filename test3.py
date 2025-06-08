###############################################################################
#  Amacan HMS Auto-Calibrator V28 (GUI Controls & Final Results)
#
#  This version adds GUI controls for Max Iterations and Target NSE, and
#  ensures the 'Results' tab always shows the best-found run at the end.
#
#  - KEY CHANGES -
#  1. Added Entry widgets and StringVars for Max Iterations and Target NSE.
#  2. `run_calibration_workflow` now uses these GUI values.
#  3. The workflow now tracks the data associated with the best run.
#  4. At the end of the process, the Results tab is always generated for the
#     best run found, regardless of whether the target NSE was met.
###############################################################################
import os
import sys
import threading
import datetime
import shutil
import subprocess
import numpy as np
import pandas as pd
from tkinter import Tk, filedialog, ttk, StringVar, scrolledtext, END, VERTICAL

# --- New imports for the 8.3 short path fix ---
import ctypes
from pathlib import Path
from ctypes import wintypes, windll, create_unicode_buffer

# --- Matplotlib setup for embedding plot in Tkinter ---
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
plt.switch_backend("Agg")

# --- DSS file reader ---
try:
    from pydsstools.heclib.dss import HecDss
except ImportError:
    print("Error: pydsstools library not found.")
    print("Please install it by running: pip install pydsstools")
    sys.exit(1)

# ────────────────────────  PARAMETER & ALGORITHM CONSTANTS  ──────────────────────── #

BASIN_FILE_MAP = {
    # SMA Loss
    'initial_soil_storage_percent': "Initial Soil Storage Percent",
    'initial_gw1_storage_percent': "Initial GW1 Storage Percent",
    'initial_gw2_storage_percent': "Initial GW2 Storage Percent",
    'soil_maximum_infiltration': "Soil Maximum Infiltration",
    'soil_storage_capacity': "Soil Storage Capacity",
    'soil_tension_capacity': "Soil Tension Capacity",
    'soil_maximum_percolation': "Soil Maximum Percolation",
    'groundwater_1_storage_capacity': "Groundwater 1 Storage Capacity",
    'groundwater_1_routing_coefficient': "Groundwater 1 Routing Coefficient",
    'groundwater_1_maximum_percolation': "Groundwater 1 Maximum Percolation",
    'groundwater_2_storage_capacity': "Groundwater 2 Storage Capacity",
    'groundwater_2_routing_coefficient': "Groundwater 2 Routing Coefficient",
    'groundwater_2_maximum_percolation': "Groundwater 2 Maximum Percolation",

    # Linear Reservoir Baseflow
    'gw_1_baseflow_fraction': "Gw 1 Baseflow Fraction",
    'gw_1_number_of_reservoirs': "Gw 1 Number Reservoirs",
    'gw_1_initial_baseflow': "Gw 1 Initial Baseflow",
    'gw_1_coefficient_baseflow' : 'GW-1 Routing Coefficient',
    'gw_2_baseflow_fraction': "Gw 2 Baseflow Fraction",
    'gw_2_number_of_reservoirs': "Gw 2 Number Reservoirs",
    'gw_2_initial_baseflow': "Gw 2 Initial Baseflow",
    'gw_2_coefficient_baseflow' : 'GW-2 Routing Coefficient',
    # Kinematic Wave Transform
    'plane_1_roughness': "Plane 1 Roughness",
    'plane_1_number_of_steps': "Plane 1 Number Of Steps",
    'plane_2_roughness': "Plane 2 Roughness",
    'plane_2_number_of_steps': "Plane 2 Number Of Steps",
    'subcollector_mannings_n': "Subcollector Mannings N",
    'subcollector_steps': "Subcollector Number Of Steps",
    'collector_mannings_n': "Collector Mannings N",
    'collector_steps': "Collector Number Of Steps",
    'channel_mannings_n': "Channel Mannings N",
    'channel_steps': "Channel Number Of Steps",
}

PARAM_RANGES = {
    # SMA Loss
    'initial_soil_storage_percent': (10.0, 90.0), 'soil_storage_capacity': (50.0, 1500.0),
    'soil_tension_capacity': (25.0, 1500.0), 'soil_maximum_infiltration': (1.0, 100.0),
    'soil_maximum_percolation': (1.0, 100.0), 'initial_gw1_storage_percent': (0.0, 100.0),
    'groundwater_1_storage_capacity': (1.0, 1500.0), 'groundwater_1_routing_coefficient': (10.0, 1000.0),
    'groundwater_1_maximum_percolation': (1.0, 50.0), 'initial_gw2_storage_percent': (0.0, 100.0),
    'groundwater_2_storage_capacity': (1.0, 1500.0), 'groundwater_2_routing_coefficient': (50.0, 1000.0),
    'groundwater_2_maximum_percolation': (1.0, 100.0),
    # Linear Reservoir Baseflow
    'gw_1_baseflow_fraction': (0.1, 1.0), 'gw_1_number_of_reservoirs': (1, 30),
    'gw_1_initial_baseflow': (0.0, 1), 'gw_2_baseflow_fraction': (0.1, 1.0),
    'gw_2_number_of_reservoirs': (1, 30), 'gw_2_initial_baseflow': (0.0, 1),
    'gw_1_coefficient_baseflow' : (10,1000), 'gw_2_coefficient_baseflow': (10,1000),
    # Kinematic Wave Transform
    'plane_1_roughness': (0.01, 0.25), 'plane_1_number_of_steps': (1, 30),
    'plane_2_roughness': (0.01, 0.25), 'plane_2_number_of_steps': (1, 30),
    'subcollector_mannings_n': (0.01, 0.25), 'subcollector_steps': (1, 30),
    'collector_mannings_n': (0.01, 0.2), 'collector_steps': (1, 30),
    'channel_mannings_n': (0.01, 0.15), 'channel_steps': (1, 10),
}
EXPLORATION_PROBABILITY = 0.20
PERTURBATION_FACTOR = 0.10

# --- Global variable to hold a reference to the failure tab frame ---
failed_run_tab_frame = None

# ─────────────────────────── SCRIPT CREATION & FILE I/O ──────────────────────────── #

def _short_path(path: str) -> str:
    """Return Windows 8.3 path if it contains spaces (no-op on other OSes)."""
    if os.name != "nt" or " " not in path: return path
    buf = create_unicode_buffer(260)
    GetShortPathNameW = windll.kernel32.GetShortPathNameW
    GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    if GetShortPathNameW(path, buf, 260): return buf.value
    return path

def create_jython_script_in_project_dir(project_dir, project_hms_path, target_run_name):
    """
    Creates a robust Jython script using the JythonHms module, which has been
    confirmed by diagnostics to be the correct API for this HEC-HMS version.
    """
    python_subfolder = os.path.join(project_dir, 'Python')
    jython_script_path = os.path.join(python_subfolder, 'run_hms.py')
    
    try:
        os.makedirs(python_subfolder, exist_ok=True)
    except Exception as e:
        print(f"\nERROR: Could not create directory '{python_subfolder}'.\nDetails: {e}")
        return None

    project_name = os.path.basename(project_hms_path).replace('.hms', '')
    project_directory = os.path.dirname(project_hms_path)

    jython_code = f"""
# HEC-Commander Jython Script for HEC-HMS
import sys
try:
    from hms.model.JythonHms import OpenProject, Compute, Exit
except ImportError:
    print("Error: This script must be run within the HEC-HMS Jython environment.")
    sys.exit(1)

projectName = r"{project_name}"
projectDir = r"{project_directory}"
targetRunName = r"{target_run_name}"

print("HEC-HMS Jython script started.")
print("Project Directory: %s" % projectDir)
print("Project Name: %s" % projectName)
print("Target run: %s" % targetRunName)

try:
    OpenProject(projectName, projectDir)
    print("Project opened successfully.")
    
    print("Attempting to compute run: '%s'..." % targetRunName)
    Compute(targetRunName)
    print("Compute command for run '{0}' executed.".format(targetRunName))

    Exit(0)
    
except Exception as e:
    print("An error occurred within the Jython script:")
    print(str(e))
    Exit(1)
"""
    try:
        with open(jython_script_path, 'w') as f:
            f.write(jython_code.strip())
        return jython_script_path
    except Exception as e:
        print(f"\nERROR: An unexpected error occurred while creating the script: {e}")
        return None

def write_basin_file_line_by_line(source_path, dest_path, new_params, target_subbasin):
    param_map_inv = {v: k for k, v in BASIN_FILE_MAP.items()}
    with open(source_path, 'r') as f_in, open(dest_path, 'w') as f_out:
        in_target_subbasin = False
        for line in f_in:
            stripped_line = line.strip()
            if stripped_line.startswith("Subbasin:"):
                current_subbasin = stripped_line.split(":", 1)[1].strip()
                in_target_subbasin = (current_subbasin == target_subbasin)
            if stripped_line == "End:":
                in_target_subbasin = False
            line_written = False
            if in_target_subbasin:
                parts = stripped_line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    if key in param_map_inv:
                        internal_key = param_map_inv[key]
                        if internal_key in new_params:
                            new_value = new_params[internal_key]
                            indent = line[:line.find(key)]
                            f_out.write(f"{indent}{key}: {new_value}\n")
                            line_written = True
            if not line_written: f_out.write(line)
    return True

def log_parameters(log_data, csv_path):
    if not os.path.exists(os.path.dirname(csv_path)):
        os.makedirs(os.path.dirname(csv_path))
    pd.DataFrame([log_data]).to_csv(csv_path, mode="a", index=False, header=not os.path.exists(csv_path))

# ────────────────────────  CORE CALIBRATION & ANALYSIS  ──────────────────────── #

def generate_parameters(target_subbasin, best_params):
    new_params = {}
    use_random_search = (best_params is None) or (np.random.rand() < EXPLORATION_PROBABILITY)
    search_type = "Exploration (Random Search)" if use_random_search else "Exploitation (Mutating Best)"
    print(f"--- Generating new parameters for {target_subbasin} ({search_type}) ---")
    for param, (min_val, max_val) in PARAM_RANGES.items():
        if use_random_search:
            if isinstance(min_val, int): new_params[param] = np.random.randint(min_val, max_val + 1)
            else: new_params[param] = round(np.random.uniform(min_val, max_val), 4)
        else:
            best_val = best_params.get(param, (min_val + max_val) / 2)
            perturb_range = (max_val - min_val) * PERTURBATION_FACTOR
            low_bound = max(min_val, best_val - perturb_range); high_bound = min(max_val, best_val + perturb_range)
            if isinstance(min_val, int): new_params[param] = np.random.randint(int(low_bound), int(high_bound) + 1)
            else: new_params[param] = round(np.random.uniform(low_bound, high_bound), 4)
    if new_params['soil_tension_capacity'] >= new_params['soil_storage_capacity']:
        print("Constraint violated: tension_capacity >= storage_capacity. Adjusting...")
        new_max = new_params['soil_storage_capacity']
        stc_min_orig, _ = PARAM_RANGES['soil_tension_capacity']
        if stc_min_orig >= new_max: new_params['soil_tension_capacity'] = round(new_max * 0.9, 4)
        else: new_params['soil_tension_capacity'] = round(np.random.uniform(stc_min_orig, new_max), 4)
        print(f"Adjusted soil_tension_capacity to: {new_params['soil_tension_capacity']}")
    if new_params['soil_maximum_infiltration'] <= 0:
        new_params['soil_maximum_infiltration'] = 0.1; print("Adjusted soil_maximum_infiltration to be > 0.")
    if new_params.get('gw_1_routing_coefficient', 1.0) <= 0:
        new_params['gw_1_routing_coefficient'] = 1.0; print("Adjusted gw_1_routing_coefficient to be > 0.")
    if new_params.get('gw_2_routing_coefficient', 1.0) <= 0:
        new_params['gw_2_routing_coefficient'] = 1.0; print("Adjusted gw_2_routing_coefficient to be > 0.")
    return new_params

def run_hms_model(hms_cmd_path, jython_script_path):
    hms_cmd_path = _short_path(os.fspath(hms_cmd_path))
    jython_script_path = _short_path(os.fspath(jython_script_path))
    
    cmd_str = f'pushd "{os.path.dirname(hms_cmd_path)}" && HEC-HMS.cmd -s "{jython_script_path}" && popd'
    
    print("--- Starting HEC-HMS Simulation ---");
    print("Command:", cmd_str)

    try:
        result = subprocess.run(
            cmd_str, shell=True, text=True,
            capture_output=True, check=True
        )
        if result.stdout: print("--- HEC-HMS STDOUT ---\n" + result.stdout)
        if result.stderr: print("--- HEC-HMS STDERR ---\n" + result.stderr)
        if 'ERROR' in result.stdout or 'FAILED' in result.stdout or 'Error' in result.stdout:
            print("HEC-HMS process finished with a failure state reported by the script.")
            return False
        print("HEC-HMS process finished successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print("ERROR: HEC-HMS simulation failed (non-zero exit code).")
        if e.stdout: print("--- HEC-HMS STDOUT ---\n" + e.stdout)
        if e.stderr: print("--- HEC-HMS STDERR ---\n" + e.stderr)
    except Exception as e:
        print(f"An unexpected Python error occurred during HMS execution: {e}")
    return False

def compute_nse(dss_filepath, dss_run_name, obs_df, target_subbasin, iteration_num): # Added iteration_num
    """
    Computes NSE for the specified target_subbasin using logic from the user's proven script.
    """
    print(f"--- Computing NSE for subbasin: {target_subbasin} ---")
    if not os.path.isfile(dss_filepath):
        print(f"ERROR: DSS file not found at '{dss_filepath}'. This can happen after a failed run.")
        return np.nan, None

    subbasin_mapping = {
        'Bunlang Catchment 1': {'ep_name': 'Bunlang EP', 'creek_name': 'Bunlang Creek'},
        'Bunlang Catchment 2': {'ep_name': 'Bunlang EP', 'creek_name': 'Bunlang Creek'},
        'Masara Catchment': {'ep_name': 'Masara EP', 'creek_name': 'Masara River'},
        'Simsimin Catchment': {'ep_name': 'Simsimin Catchment', 'creek_name': 'Simsimin Creek'}
    }

    if target_subbasin not in subbasin_mapping:
        print(f"Error: No DSS mapping for subbasin '{target_subbasin}'. Please update 'subbasin_mapping' dictionary.")
        return np.nan, None

    mapping_info = subbasin_mapping[target_subbasin]
    ep_name = mapping_info['ep_name']
    creek_name = mapping_info['creek_name']
    
    df_merged = pd.DataFrame() 

    try:
        with HecDss.Open(dss_filepath) as dss:
            dss_path_query = f"//{ep_name}/FLOW/01JAN2025/1DAY/RUN:{dss_run_name.upper()}/"
            print(f"Querying DSS file with path: {dss_path_query}")
            
            ts = dss.read_ts(dss_path_query, window=('02Feb2025 00:00:00','08Apr2025 00:00:00'), trim_missing=True)
            
            df_ts = pd.DataFrame({'date': np.array(ts.pytimes), 'pred_value': ts.values})
            if df_ts.empty:
                print("Error: No simulated data found in DSS file for the given path and time window.")
                return np.nan, df_merged

            allowed_dates = pd.to_datetime([
                "03/02/2025","07/02/2025","10/02/2025","12/02/2025","14/02/2025",
                "17/02/2025","19/02/2025","03/03/2025","05/03/2025","07/03/2025",
                "12/03/2025","17/03/2025","24/03/2025","26/03/2025","28/03/2025",
                "31/03/2025","02/04/2025","07/04/2025"], dayfirst=True)

            df_sim = df_ts[df_ts['date'].isin(allowed_dates)].reset_index(drop=True)
            
            df_obs_f = obs_df[obs_df['extraction_point'] == creek_name].copy()
            df_obs_f['date'] = pd.to_datetime(df_obs_f['date'])

            df_merged = pd.merge(df_obs_f, df_sim, on='date')
            
            if len(df_merged) < 2:
                print(f"Error: < 2 matching dates between observed and simulated data for '{ep_name}'.")
                return np.nan, df_merged

            mean_obs = df_merged['discharge'].mean()
            numerator = ((df_merged['discharge'] - df_merged['pred_value'])**2).sum()
            denominator = ((df_merged['discharge'] - mean_obs)**2).sum()
            
            if denominator == 0:
                print("Warning: Denominator in NSE is zero. Cannot compute.")
                return np.nan, df_merged

            nse = 1 - (numerator / denominator)
            # **MODIFIED PRINT STATEMENT**
            print(f"Run {iteration_num} | NSE for {ep_name}: {nse:.4f}")
            return nse, df_merged

    except Exception as e:
        print(f"An unexpected error occurred during NSE Calculation.\nDetails: {e}")
        return np.nan, df_merged

def plot_final_results(df_merged, target_subbasin, nse):
    """
    Plots the final calibration result for the target subbasin.
    """
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.scatter(df_merged['date'], df_merged['discharge'], marker='o', color='r', label='Observed')
    ax.plot(df_merged['date'], df_merged['pred_value'], '-+', color='b', label='Simulated')
    ax.set_title(f'Best Calibration Result for {target_subbasin}\nFinal NSE: {nse:.4f}', fontsize=16)
    ax.set_xlabel('Date')
    ax.set_ylabel('Discharge (cms)')
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.legend()
    fig.tight_layout()
    return fig

# ────────────────────────────  TKINTER GUI & WORKFLOW  ──────────────────────────────── #
class RedirectToText:
    def __init__(self, text_widget): self.text_widget = text_widget
    def write(self, s): self.text_widget.insert(END, s); self.text_widget.see(END)
    def flush(self): pass

def display_results_tabs(best_params, df_merged, target_subbasin, nse):
    for widget in results_tab_frame.winfo_children(): widget.destroy()
    notebook = ttk.Notebook(results_tab_frame); notebook.pack(fill='both', expand=True, padx=5, pady=5)
    plot_frame = ttk.Frame(notebook); params_frame = ttk.Frame(notebook)
    notebook.add(plot_frame, text='Hydrograph Plot'); notebook.add(params_frame, text='Best Parameters')
    
    # Pass the merged dataframe from the best run to the plotting function
    fig = plot_final_results(df_merged, target_subbasin, nse)
    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw(); canvas.get_tk_widget().pack(fill='both', expand=True)

    cols = ('Parameter', 'Value'); tree = ttk.Treeview(params_frame, columns=cols, show='headings')
    tree.heading('Parameter', text='Parameter'); tree.heading('Value', text='Value')
    tree.column('Parameter', width=300)
    if best_params:
        for param, value in best_params.items():
            tree.insert('', END, values=(param, value))
    tree.pack(fill='both', expand=True, padx=5, pady=5)
    main_tab_control.select(results_tab_frame)

def display_failed_run_tab(params):
    global failed_run_tab_frame
    if failed_run_tab_frame:
        try: main_tab_control.forget(failed_run_tab_frame)
        except Exception: pass
        failed_run_tab_frame.destroy()
    failed_run_tab_frame = ttk.Frame(main_tab_control); main_tab_control.add(failed_run_tab_frame, text='Last Failed Run')
    cols = ('Parameter', 'Value'); tree = ttk.Treeview(failed_run_tab_frame, columns=cols, show='headings')
    tree.heading('Parameter', text='Parameter'); tree.heading('Value', text='Value')
    tree.column('Parameter', width=300)
    if params:
        for param, value in params.items():
            tree.insert('', END, values=(param, value))
    tree.pack(fill='both', expand=True, padx=5, pady=5)
    main_tab_control.select(failed_run_tab_frame)

def run_calibration_workflow():
    # --- Get all settings from GUI ---
    hms_install_dir = hms_dir_var.get()
    project_dir = project_dir_var.get()
    basin_name = basin_name_var.get()
    hms_filename = hms_filename_var.get()
    dss_name = dss_run_name_var.get()
    target_run_name = target_run_name_var.get()
    xl_path = obs_xl_var.get()
    target_subbasin = target_subbasin_var.get()

    try:
        max_iterations = int(max_iter_var.get())
        target_nse = float(target_nse_var.get())
    except (ValueError, TypeError):
        print("ERROR: Max Iterations and Target NSE must be valid numbers.")
        return

    if not all([hms_install_dir, project_dir, basin_name, hms_filename, dss_name, target_run_name, xl_path, target_subbasin]):
        print("ERROR: Please fill in all fields before starting."); return
    
    # --- Set up paths and backup ---
    project_dir = os.path.normpath(project_dir)
    hms_install_dir = os.path.normpath(hms_install_dir)
    xl_path = os.path.normpath(xl_path)
    hms_cmd_path = os.path.join(hms_install_dir, 'HEC-HMS.cmd')
    basin_path = os.path.join(project_dir, basin_name)
    project_hms_path = os.path.join(project_dir, hms_filename)
    dss_path = os.path.join(project_dir, f"{dss_name}.dss")
    csv_path = os.path.join(project_dir, 'calibration_log.csv')
    
    print("\n" + "─"*20 + "  CALIBRATION STARTED  " + "─"*20)
    basin_backup_path = f"{basin_path}.backup"
    
    try:
        shutil.copy(basin_path, basin_backup_path); print(f"Original basin file backed up.")
        global df_obs; df_obs = pd.read_excel(xl_path)
    except Exception as e:
        print(f"ERROR during setup: {e}"); return
        
    # --- Initialize calibration loop variables ---
    best_nse = -np.inf
    best_params = None
    best_df_merged = None # To store the data for the best run
    iteration = 0
    
    # --- Main Calibration Loop ---
    while best_nse < target_nse and iteration < max_iterations:
        iteration += 1
        current_params = generate_parameters(target_subbasin, best_params)
        
        jython_script_path = create_jython_script_in_project_dir(project_dir, project_hms_path, target_run_name)
        if not jython_script_path:
            print("Halting calibration: Jython script creation failed."); break
            
        write_basin_file_line_by_line(basin_backup_path, basin_path, current_params, target_subbasin)
        
        run_ok = run_hms_model(hms_cmd_path, jython_script_path)
        if not run_ok:
            print(f"Run {iteration} failed – logging parameters and continuing.")
            display_failed_run_tab(current_params); continue
        
        # **UPDATED FUNCTION CALL**
        current_nse, df_merged = compute_nse(dss_path, dss_name, df_obs, target_subbasin, iteration)
        
        log_parameters({'run_id': f"Run_{iteration}", 'nse': current_nse, **current_params.copy()}, csv_path)
        
        if pd.isna(current_nse):
            print("NSE calculation failed. Continuing to next iteration."); continue
            
        if current_nse > best_nse:
            print(f"NEW BEST FOUND! Iteration: {iteration}, NSE: {current_nse:.4f} (previously {best_nse:.4f})")
            best_nse = current_nse
            best_params = current_params
            best_df_merged = df_merged.copy() 

    # --- Post-Calibration Summary and Cleanup ---
    if best_nse >= target_nse:
        print(f"\nSUCCESS! Target NSE of {target_nse} reached in iteration {iteration}.")
    elif iteration >= max_iterations:
        print(f"\nSTOPPED: Max iterations ({max_iterations}) reached.")
    else:
        print(f"\nCalibration finished before reaching target NSE.")

    if best_params and best_df_merged is not None:
        print(f"Displaying results for the best run found (NSE = {best_nse:.4f})")
        display_results_tabs(best_params, best_df_merged, target_subbasin, best_nse)
    else:
        print("No successful simulation runs were completed.")

    shutil.move(basin_backup_path, basin_path)
    print("\n" + "─"*21 + "  RUN FINISHED  " + "─"*21 + "\nOriginal basin file has been restored.")

def start_thread():
    run_button.config(state="disabled")
    threading.Thread(target=run_calibration_workflow, daemon=True).start()
    root.after(1000, lambda: run_button.config(state="normal"))

root = Tk(); root.title("Amacan HMS Auto-Calibrator v28"); root.geometry("850x950")
main_paned_window = ttk.PanedWindow(root, orient=VERTICAL); main_paned_window.pack(fill='both', expand=True)
input_frame = ttk.LabelFrame(main_paned_window, text="Setup", padding=10); main_paned_window.add(input_frame, weight=0)
def add_input_row(label, var, is_dir=False, is_file=False):
    row = ttk.Frame(input_frame)
    row.pack(fill='x', pady=2); ttk.Label(row, text=label, width=23).pack(side='left')
    ttk.Entry(row, textvariable=var).pack(side='left', fill='x', expand=True, padx=5)
    if is_dir or is_file:
        filetypes = [("Excel files", "*.xlsx"), ("All files", "*.*")] if "Observed" in label else None
        cmd = (lambda: var.set(filedialog.askdirectory())) if is_dir else (lambda: var.set(filedialog.askopenfilename(filetypes=filetypes)))
        ttk.Button(row, text="Browse...", width=10, command=cmd).pack(side='left')

bottom_frame = ttk.Frame(main_paned_window); main_paned_window.add(bottom_frame, weight=1)
main_tab_control = ttk.Notebook(bottom_frame); main_tab_control.pack(expand=1, fill="both")
log_tab = ttk.Frame(main_tab_control); main_tab_control.add(log_tab, text='Log')
results_tab_frame = ttk.Frame(main_tab_control); main_tab_control.add(results_tab_frame, text='Results')
log_text = scrolledtext.ScrolledText(log_tab, height=10, wrap='word'); log_text.pack(fill='both', expand=True, padx=5, pady=5)
sys.stdout = RedirectToText(log_text); sys.stderr = RedirectToText(log_text)

# --- USER DEFAULT VALUES ARE SET HERE ---
hms_dir_var = StringVar(value="C:/Program Files/HEC/HEC-HMS/4.12")
project_dir_var = StringVar(value="C:/Users/richmond/Downloads/hms_edc_amacan_autotest_CALIBRATION")
basin_name_var = StringVar(value="EDC_Basin.basin")
hms_filename_var = StringVar(value="hms_edc_amacan.hms")
dss_run_name_var = StringVar(value="edc_run_v2")
target_run_name_var = StringVar(value="edc_run_v2")
obs_xl_var = StringVar(value="C:/Users/richmond/Downloads/hms_edc_amacan_autotest_CALIBRATION/NSE_computation/observed_data.xlsx")
target_subbasin_var = StringVar(value="Simsimin Catchment")
# New GUI variables
max_iter_var = StringVar(value="10000")
target_nse_var = StringVar(value="0.51")

add_input_row("HEC-HMS Install Directory:", hms_dir_var, is_dir=True)
add_input_row("HMS Project Directory:", project_dir_var, is_dir=True)
add_input_row("Basin File Name:", basin_name_var)
add_input_row("HMS File Name (.hms):", hms_filename_var)
add_input_row("DSS Run Name:", dss_run_name_var)
add_input_row("Target Run Name:", target_run_name_var)
add_input_row("Observed Data (*.xlsx):", obs_xl_var, is_file=True)
add_input_row("Target Subbasin:", target_subbasin_var)
# New GUI rows
add_input_row("Max Iterations:", max_iter_var)
add_input_row("Target NSE:", target_nse_var)

run_button = ttk.Button(input_frame, text="Start Calibration", command=start_thread)
run_button.pack(pady=10, fill='x', ipady=5)
root.mainloop()