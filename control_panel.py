import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import sys
import os
import signal
import psutil
import time
from datetime import datetime

class ServerControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Flask Server Control Panel")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        # Server process
        self.server_process = None
        self.server_running = False
        self.server_pid = None
        
        # Create GUI
        self.create_widgets()
        
        # Check for existing server process on startup
        self.check_existing_server()
        
        # Start status update thread
        self.start_status_updater()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Flask Server Control Panel", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Server status
        status_frame = ttk.LabelFrame(main_frame, text="Server Status", padding="10")
        status_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(1, weight=1)
        
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.status_label = ttk.Label(status_frame, text="Stopped", foreground="red", font=("Arial", 10, "bold"))
        self.status_label.grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(status_frame, text="URL:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        self.url_label = ttk.Label(status_frame, text="http://localhost:5000", foreground="blue")
        self.url_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(status_frame, text="PID:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10))
        self.pid_label = ttk.Label(status_frame, text="N/A")
        self.pid_label.grid(row=2, column=1, sticky=tk.W)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Server", command=self.start_server, style="Accent.TButton")
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="Stop Server", command=self.stop_server, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.restart_button = ttk.Button(button_frame, text="Restart Server", command=self.restart_server, state="disabled")
        self.restart_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.open_browser_button = ttk.Button(button_frame, text="Open in Browser", command=self.open_browser, state="disabled")
        self.open_browser_button.pack(side=tk.LEFT)
        
        # Server output log
        log_frame = ttk.LabelFrame(main_frame, text="Server Output", padding="10")
        log_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state="disabled", wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Clear log button
        clear_button = ttk.Button(log_frame, text="Clear Log", command=self.clear_log)
        clear_button.grid(row=1, column=0, sticky=tk.E, pady=(5, 0))
        
    def log_message(self, message):
        """Add message to log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        
    def clear_log(self):
        """Clear the log text"""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")
        
    def check_existing_server(self):
        """Check if server is already running on port 5000"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('app.py' in arg for arg in cmdline):
                        # Check if it's using port 5000
                        connections = proc.connections()
                        for conn in connections:
                            if conn.laddr.port == 5000:
                                self.server_pid = proc.info['pid']
                                self.server_running = True
                                self.update_ui_state()
                                self.log_message(f"Found existing server process (PID: {self.server_pid})")
                                return
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception as e:
            self.log_message(f"Error checking for existing server: {e}")
            
    def start_server(self):
        """Start the Flask server"""
        if self.server_running:
            messagebox.showwarning("Warning", "Server is already running!")
            return
            
        try:
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            app_path = os.path.join(script_dir, "app.py")
            
            if not os.path.exists(app_path):
                messagebox.showerror("Error", f"app.py not found at {app_path}")
                return
                
            self.log_message("Starting Flask server...")
            
            # Start server process
            self.server_process = subprocess.Popen(
                [sys.executable, app_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=script_dir
            )
            
            self.server_pid = self.server_process.pid
            self.server_running = True
            self.update_ui_state()
            
            self.log_message(f"Server started with PID: {self.server_pid}")
            
            # Start thread to read server output
            threading.Thread(target=self.read_server_output, daemon=True).start()
            
        except Exception as e:
            self.log_message(f"Error starting server: {e}")
            messagebox.showerror("Error", f"Failed to start server: {e}")
            
    def stop_server(self):
        """Stop the Flask server"""
        if not self.server_running:
            messagebox.showwarning("Warning", "Server is not running!")
            return
            
        try:
            self.log_message("Stopping Flask server...")
            
            if self.server_process:
                # Try graceful termination first
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    self.server_process.kill()
                    self.server_process.wait()
                    
                self.server_process = None
                
            # Also try to kill by PID if we have it
            elif self.server_pid:
                try:
                    proc = psutil.Process(self.server_pid)
                    proc.terminate()
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass  # Process already dead
                    
            self.server_running = False
            self.server_pid = None
            self.update_ui_state()
            self.log_message("Server stopped successfully")
            
        except Exception as e:
            self.log_message(f"Error stopping server: {e}")
            messagebox.showerror("Error", f"Failed to stop server: {e}")
            
    def restart_server(self):
        """Restart the Flask server"""
        self.log_message("Restarting server...")
        self.stop_server()
        time.sleep(2)  # Give it a moment to fully stop
        self.start_server()
        
    def open_browser(self):
        """Open the server URL in default browser"""
        import webbrowser
        url = "http://localhost:5000"
        webbrowser.open(url)
        self.log_message(f"Opened {url} in browser")
        
    def read_server_output(self):
        """Read and display server output in a separate thread"""
        if not self.server_process:
            return
            
        try:
            for line in iter(self.server_process.stdout.readline, ''):
                if line:
                    # Schedule the UI update in the main thread
                    self.root.after(0, self.log_message, line.strip())
                    
                # Check if process is still running
                if self.server_process.poll() is not None:
                    break
                    
        except Exception as e:
            self.root.after(0, self.log_message, f"Error reading server output: {e}")
            
        # Process ended
        self.root.after(0, self.on_server_ended)
        
    def on_server_ended(self):
        """Handle when server process ends"""
        if self.server_process:
            return_code = self.server_process.poll()
            if return_code is not None:
                self.log_message(f"Server process ended with return code: {return_code}")
                self.server_process = None
                self.server_running = False
                self.server_pid = None
                self.update_ui_state()
                
    def update_ui_state(self):
        """Update UI elements based on server state"""
        if self.server_running:
            self.status_label.config(text="Running", foreground="green")
            self.pid_label.config(text=str(self.server_pid) if self.server_pid else "Unknown")
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.restart_button.config(state="normal")
            self.open_browser_button.config(state="normal")
        else:
            self.status_label.config(text="Stopped", foreground="red")
            self.pid_label.config(text="N/A")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.restart_button.config(state="disabled")
            self.open_browser_button.config(state="disabled")
            
    def start_status_updater(self):
        """Start a thread to periodically check server status"""
        def update_status():
            while True:
                time.sleep(5)  # Check every 5 seconds
                
                if self.server_running and self.server_pid:
                    try:
                        # Check if process is still running
                        proc = psutil.Process(self.server_pid)
                        if not proc.is_running():
                            self.root.after(0, self.on_server_ended)
                    except psutil.NoSuchProcess:
                        self.root.after(0, self.on_server_ended)
                        
        threading.Thread(target=update_status, daemon=True).start()
        
    def on_closing(self):
        """Handle application closing"""
        if self.server_running:
            result = messagebox.askyesno("Confirm Exit", 
                                       "Server is still running. Do you want to stop it and exit?")
            if result:
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    root = tk.Tk()
    
    # Set up ttk style
    style = ttk.Style()
    style.theme_use('clam')  # Use a modern theme
    
    # Create control panel
    control_panel = ServerControlPanel(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", control_panel.on_closing)
    
    # Center window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")
    
    # Start the GUI
    root.mainloop()

if __name__ == "__main__":
    main()
