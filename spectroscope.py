""" Python app for the USB spectroscope.
Version 0.1, made by Dmitrii, Feb 2026, (dmitryelj@gmail.com)
"""

import cv2
import datetime
import tkinter as tk
import numpy as np
from PIL import Image, ImageTk
from typing import Optional, Any
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Video source: usually, 0 = standard webcam, 1 = USB spectrometer 
video_source = 1


class SpectrometerApp:
    calibration = (
        (305, 405),  # Mercury, 405nm
        (707, 631),  # Europium, 631nm  
    )
    FRAME_WIDTH = 1280
    FRAME_HEIGHT = 720

    def __init__(self, window, video_source=0):
        self.window = window
        self.window.title("PySpectroscope v0.1")
        
        # Initialize OpenCV video capture
        self.vid = cv2.VideoCapture(video_source)
        self.vid.set(cv2.CAP_PROP_FRAME_WIDTH, self.FRAME_WIDTH)
        self.vid.set(cv2.CAP_PROP_FRAME_HEIGHT, self.FRAME_HEIGHT)
        self._current_frame: Optional[np.array] = None

        # Matplotlib Setup
        self.fig, self.ax = plt.subplots(figsize=(9, 6), dpi=80)
        self.fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.10)
        # Create an object that we will update dynamically
        self.lc = LineCollection([], linewidth=2)
        self.ax.add_collection(self.lc)
        self.pc = PolyCollection([], facecolors=[], edgecolors=[], alpha=0.8)
        self.ax.add_collection(self.pc)
        self._set_ax_style()

        # Integrate Matplotlib with Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.window)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Add an overlay spectrometer image
        self.overlay_image = tk.Label(self.window, borderwidth=2, relief="solid")
        # 'relx' and 'rely' position it relative to the window (0.0 to 1.0)
        # 'anchor="ne"' means the North-East corner of the widget is at the specified point
        self.overlay_image.place(relx=0.96, rely=0.08, anchor="ne", width=320, height=240)
        self.overlay_tk_img: Image = None

        # Create a control panel at the bottom
        self.btn_frame = tk.Frame(window)
        self.btn_frame.pack(side=tk.BOTTOM, fill=tk.X)
        # "Save" Button
        self.save_btn = tk.Button(
            self.btn_frame, 
            text="Save Spectrum", 
            command=self._save_snapshot,
            fg="#1a1a1a",
        )
        self.save_btn.grid(row=0, column=0, padx=(20, 0))
        # Status Label
        self.status_lbl = tk.Label(self.btn_frame, text="Ready", padx=10)
        self.status_lbl.grid(row=0, column=1, padx=25, pady=10)
 
    def __del__(self):
        """Release the capture device when the window is closed"""
        if self.vid.isOpened():
            self.vid.release()

    def run_forever(self):
        """Run the app"""
        self.update()
        self.window.mainloop()

    def update(self):
        """Get a frame from the video source"""
        ret, frame = self.vid.read()        
        if ret:
            self._draw_spectrum(frame)
            self._draw_overlay(frame)
            self._current_frame = frame
            
            # Redraw the canvas when ready
            self.canvas.draw_idle()
        
        # Call this function again after 30 milliseconds (~30 FPS)
        self.window.after(30, self.update)

    def _draw_overlay(self, frame: np.array):
        """Update the Overlay Image"""
        # Resize to the thumbnail size
        overlay_w = self.overlay_image.winfo_width()
        overlay_h = self.overlay_image.winfo_height()
        small_frame = cv2.resize(frame, (overlay_w, overlay_h))
        # Update
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        self.overlay_tk_img = ImageTk.PhotoImage(image=Image.fromarray(rgb_frame))
        self.overlay_image.configure(image=self.overlay_tk_img)

    def _draw_spectrum(self, frame: np.array):
        """Draw spectrum data"""
        height, width, _ = frame.shape

        # Extract central line intensity
        mid_y = height // 2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        intensity_line = gray[mid_y, :]

        # Update graph line
        colors = [self._px_to_rgb(px, max_intensity=0.5) for px in range(width - 1)]
        segments = [[(px, intensity_line[px]), (px+1, intensity_line[px+1])] for px in range(width - 1)]
        self.lc.set_segments(segments)
        self.lc.set_color(colors)

        # Update the area under the segments
        colors = [self._px_to_rgb(px) for px in range(width - 1)]
        vertices = [[(px, 0), (px, intensity_line[px]), (px+1, intensity_line[px+1]), (px+1, 0)] for px in range(width - 1)]
        self.pc.set_verts(vertices)
        self.pc.set_facecolor(colors)
        self.pc.set_edgecolor(colors)        

    def _set_ax_style(self):
        """Set axis text and style"""
        self._set_ax_ticks()
        self._set_ax_limit()
        self.ax.set_ylabel("Intensity")
        self.ax.set_xlabel("Wavelength, nm")
        self.ax.spines["top"].set_color("lightgray")
        self.ax.spines["right"].set_color("lightgray")
        self.ax.grid(visible=True, linestyle='--', linewidth=0.5, color="gray", alpha=0.5)

    def _set_ax_limit(self):
        """Set axis limits"""
        self.ax.set_ylim(0, 255)  # RGB range
        self.ax.set_xlim(0, self.FRAME_WIDTH)

    def _set_ax_ticks(self):
        """Set axis ticks"""
        start_nm = int(self._px_to_nm(0))
        end_nm = int(self._px_to_nm(self.FRAME_WIDTH))
        # Create a list of 'round' nanometer values (e.g., 400, 450, 500...)
        nm_ticks = np.arange((start_nm // 50 + 1) * 50, end_nm, 50)
        # Convert those nanometers back to pixel positions
        pixel_ticks = [self._nm_to_px(nm) for nm in nm_ticks]
        self.ax.xaxis.set_major_locator(ticker.FixedLocator(pixel_ticks))
        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(self._px_to_nm_str))
        self.ax.tick_params(axis="x", labelsize=7)

    def _nm_to_px(self, nm: int):
        """Convert wavelength in nm to x coordinate"""
        px0, px1 = self.calibration[0][0], self.calibration[1][0]
        nm0, nm1 = self.calibration[0][1], self.calibration[1][1]
        nm_range = abs(nm0 - nm1)
        px_range = abs(px0 - px1)
        pxpernm = px_range/nm_range
        return px0 + (nm - nm0)*pxpernm

    def _px_to_nm(self, x: int):
        """Convert x coordinate to wavelength in nm"""
        px0, px1 = self.calibration[0][0], self.calibration[1][0]
        nm0, nm1 = self.calibration[0][1], self.calibration[1][1]
        nm_range = abs(nm0 - nm1)
        px_range = abs(px0 - px1)
        nmperpx = nm_range/px_range
        return nm0 + (x - px0)*nmperpx
    
    def _px_to_nm_str(self, x: int, _: Any):
        """Make the wavelength value as a string"""
        return f"{int(self._px_to_nm(x))}"

    def _px_to_rgb(self, x: int, max_intensity=1.0):
        """Convert x coordinate to RGB color"""
        nm = self._px_to_nm(x)
        return self._wavelength_to_rgb(nm, max_intensity)
    
    def _wavelength_to_rgb(self, nm: float, max_intensity: float):
        """Convert wavelength to RGB colors"""
        # From: https://www.codedrome.com/exploring-the-visible-spectrum-in-python/
        # returns RGB vals for a given wavelength
        gamma = 0.8
        
        r = g = b = 0.0
        if 380 <= nm < 440:
            r = -(nm - 440) / (440 - 380)
            b = 1.0
        elif 440 <= nm < 490:
            g = (nm - 440) / (490 - 440)
            b = 1.0
        elif 490 <= nm < 510:
            g = 1.0
            b = -(nm - 510) / (510 - 490)
        elif 510 <= nm < 580:
            r = (nm - 510) / (580 - 510)
            g = 1.0
        elif 580 <= nm < 645:
            r = 1.0
            g = -(nm - 645) / (645 - 580)
        elif 645 <= nm <= 780:
            r = 1.0

        factor = 0.0
        if 380 <= nm < 420:
            factor = 0.3 + 0.7 * (nm - 380) / (420 - 380)
        elif 420 <= nm < 701:
            factor = 1.0
        elif 701 <= nm <= 780:
            factor = 0.3 + 0.7 * (780 - nm) / (780 - 700)

        def adjust(color):
            return max_intensity * ((color * factor) ** gamma) if color > 0 else 0

        return adjust(r), adjust(g), adjust(b)
    
    def _save_snapshot(self):
        """Save the current frame into a PNG file"""
        if self._current_frame is None:
            return
        
        # Save original frame
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"spectrum_{timestamp}.png"
        cv2.imwrite(filename, self._current_frame)

        # Save graph
        self.fig.savefig(f"spectrum_{timestamp}_graph.png", dpi=300, bbox_inches="tight")

        self.status_lbl.config(text=f"File spectrum_{timestamp}.png saved")


if __name__ == "__main__":
    app = SpectrometerApp(tk.Tk(), video_source)
    app.run_forever()
