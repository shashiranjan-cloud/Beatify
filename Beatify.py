import threading
import urllib.parse
import webbrowser
import io
import sys

try:
    import requests
except Exception:
    print("This script requires the 'requests' package. Install with: pip install requests", file=sys.stderr)
    raise

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

import tkinter as tk
from tkinter import ttk, messagebox

# Suggested moods/keywords
MOODS = ["happy", "sad", "relaxed", "energetic", "romantic", "focus", "chill", "study", "workout"]

# Region/market options and how they influence the query:
# - country: iTunes country code used in the API call
# - append: keyword appended to the search term to bias results
REGION_MAP = {
    "Any": {"country": "US", "append": ""},
    "Bollywood": {"country": "IN", "append": "Bollywood"},
    "Hollywood": {"country": "US", "append": "Hollywood"},
    "Punjabi": {"country": "IN", "append": "Punjabi"},
    "Haryanvi": {"country": "IN", "append": "Haryanvi"},
    "Hindi": {"country": "IN", "append": "Hindi"},
    "International": {"country": "US", "append": ""},
    "Latin": {"country": "US", "append": "Latin"},
    "K-Pop": {"country": "KR", "append": "K-Pop"},
    "Regional (India)": {"country": "IN", "append": ""},
}

def itunes_search_url(term: str, limit: int = 25, country: str = "US") -> str:
    q = urllib.parse.quote_plus(term)
    return f"https://itunes.apple.com/search?term={q}&entity=song&limit={limit}&country={country}"

class MoodITunesApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mood -> Songs (iTunes API)")
        self.geometry("820x560")
        self.resizable(True, True)

        self.moods = sorted(MOODS)
        self.regions = list(REGION_MAP.keys())
        self.current_results = []  # list of dicts from iTunes
        self.artwork_cache = {}  # url -> PhotoImage

        self.create_widgets()

    def create_widgets(self):
        frm_top = ttk.Frame(self, padding=10)
        frm_top.pack(fill="x")

        ttk.Label(frm_top, text="Choose a mood:").grid(row=0, column=0, sticky="w")
        self.mood_cb = ttk.Combobox(frm_top, values=[m.capitalize() for m in self.moods], state="readonly", width=22)
        self.mood_cb.grid(row=0, column=1, padx=6, sticky="w")

        ttk.Label(frm_top, text="Or enter custom mood/keyword:").grid(row=1, column=0, pady=(8, 0), sticky="w")
        self.custom_entry = ttk.Entry(frm_top, width=40)
        self.custom_entry.grid(row=1, column=1, pady=(8, 0), sticky="w")
        self.custom_entry.bind("<Return>", lambda e: self.on_get_songs())

        # New: Region / Market selector
        ttk.Label(frm_top, text="Choose region/market:").grid(row=0, column=2, padx=(18,0), sticky="w")
        self.region_cb = ttk.Combobox(frm_top, values=self.regions, state="readonly", width=20)
        self.region_cb.grid(row=0, column=3, padx=(6,0), sticky="w")
        self.region_cb.set("Any")

        btn_frame = ttk.Frame(frm_top)
        btn_frame.grid(row=0, column=4, rowspan=2, padx=(12, 0))

        self.btn_get = ttk.Button(btn_frame, text="Search iTunes", command=self.on_get_songs)
        self.btn_get.pack(fill="x")

        self.status_var = tk.StringVar(value="Select a mood, choose a region, or enter a custom keyword, then click Search iTunes.")
        self.status_label = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_label.pack(side="bottom", fill="x")

        # Middle: list of songs + artwork pane
        frm_mid = ttk.Frame(self, padding=10)
        frm_mid.pack(fill="both", expand=True)

        # Left: listbox of results
        left = ttk.Frame(frm_mid)
        left.pack(side="left", fill="both", expand=True)

        self.song_listbox = tk.Listbox(left, height=22, activestyle="none")
        self.song_listbox.pack(side="left", fill="both", expand=True)
        self.song_listbox.bind("<<ListboxSelect>>", lambda e: self.on_selection_changed())
        self.song_listbox.bind("<Double-Button-1>", lambda e: self.play_preview())

        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.song_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.song_listbox.config(yscrollcommand=scrollbar.set)

        # Right: artwork and action buttons
        right = ttk.Frame(frm_mid, width=320)
        right.pack(side="right", fill="y", padx=(12, 0))

        self.artwork_label = ttk.Label(right)
        self.artwork_label.pack(pady=(0, 8))

        info_frame = ttk.Frame(right)
        info_frame.pack(fill="x")

        self.track_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.track_var, wraplength=300, justify="left", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        self.artist_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.artist_var, wraplength=300, justify="left", foreground="gray").pack(anchor="w")

        btns = ttk.Frame(right)
        btns.pack(pady=(12, 0), fill="x")

        self.btn_preview = ttk.Button(btns, text="Play Preview (30s)", command=self.play_preview)
        self.btn_preview.pack(fill="x", pady=(0, 6))

        self.btn_open_itunes = ttk.Button(btns, text="Open in iTunes/Apple Music", command=self.open_itunes)
        self.btn_open_itunes.pack(fill="x", pady=(0, 6))

        self.btn_youtube_spotify = ttk.Button(btns, text="Open YouTube & Spotify search", command=self.open_youtube_spotify)
        self.btn_youtube_spotify.pack(fill="x")

    def on_get_songs(self):
        # Determine search term and country based on mood/custom input and selected region
        custom = self.custom_entry.get().strip()
        mood_sel = self.mood_cb.get().strip().lower()
        region_sel = self.region_cb.get().strip() or "Any"
        region_info = REGION_MAP.get(region_sel, {"country": "US", "append": ""})
        country = region_info.get("country", "US")
        append = region_info.get("append", "")

        if custom:
            # If user provided a custom term, append region keyword if present
            term = f"{custom} {append}".strip()
        else:
            if mood_sel:
                term = f"{mood_sel} song {append}".strip()
            else:
                messagebox.showinfo("No input", "Please select a mood or enter a custom search term.")
                return

        # run API fetch in background thread
        self.status_var.set(f"Searching iTunes for: {term} (region: {region_sel}) ...")
        self.btn_get.config(state="disabled")
        threading.Thread(target=self.fetch_itunes, args=(term, country), daemon=True).start()

    def fetch_itunes(self, term: str, country: str):
        try:
            url = itunes_search_url(term, limit=50, country=country)
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
        except Exception as ex:
            self.after(0, lambda: self.fetch_failed(ex))
            return
        # update UI with results
        self.after(0, lambda: self.update_results(results, term, country))

    def fetch_failed(self, ex):
        self.btn_get.config(state="normal")
        self.status_var.set("Search failed.")
        messagebox.showerror("Search failed", f"Could not fetch results from iTunes: {ex}")

    def update_results(self, results, term, country):
        self.btn_get.config(state="normal")
        self.current_results = results
        self.song_listbox.delete(0, tk.END)
        self.artwork_label.config(image="", text="")
        self.artwork_cache.clear()
        if not results:
            self.status_var.set(f'No results from iTunes for "{term}" (country={country}).')
            return
        for r in results:
            name = r.get("trackName", "Unknown")
            artist = r.get("artistName", "")
            collection = r.get("collectionName", "")
            line = f"{name} — {artist}"
            if collection:
                line += f"  ({collection})"
            self.song_listbox.insert(tk.END, line)
        self.status_var.set(f'Showing {len(results)} results for "{term}" (country={country}). Select a song to see details.')

    def on_selection_changed(self):
        sel = self.song_listbox.curselection()
        if not sel:
            self.track_var.set("")
            self.artist_var.set("")
            self.artwork_label.config(image="", text="")
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.current_results):
            return
        item = self.current_results[idx]
        track = item.get("trackName", "")
        artist = item.get("artistName", "")
        self.track_var.set(track)
        self.artist_var.set(artist)
        artwork = item.get("artworkUrl100") or item.get("artworkUrl60")
        if artwork and PIL_AVAILABLE:
            # load artwork in background if not cached
            if artwork in self.artwork_cache:
                self.artwork_label.config(image=self.artwork_cache[artwork], text="")
            else:
                threading.Thread(target=self.load_artwork, args=(artwork,), daemon=True).start()
        else:
            # clear or show placeholder text
            if not PIL_AVAILABLE and artwork:
                self.artwork_label.config(text="[Install Pillow to show artwork]")
            else:
                self.artwork_label.config(image="", text="")

    def load_artwork(self, url):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img_data = resp.content
            image = Image.open(io.BytesIO(img_data)).convert("RGBA")
            image = image.resize((300, 300), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.artwork_cache[url] = photo
            self.after(0, lambda: self._apply_artwork_if_selected(url))
        except Exception:
            pass

    def _apply_artwork_if_selected(self, url):
        sel = self.song_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.current_results):
            return
        item = self.current_results[idx]
        artwork = item.get("artworkUrl100") or item.get("artworkUrl60")
        if artwork == url and url in self.artwork_cache:
            self.artwork_label.config(image=self.artwork_cache[url], text="")

    def get_selected_item(self):
        sel = self.song_listbox.curselection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a song from the list.")
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self.current_results):
            messagebox.showinfo("No selection", "Please select a valid song from the list.")
            return None
        return self.current_results[idx]

    def play_preview(self):
        item = self.get_selected_item()
        if not item:
            return
        preview = item.get("previewUrl")
        if not preview:
            messagebox.showinfo("No preview available", "No preview audio is available for this track.")
            return
        webbrowser.open_new_tab(preview)
        self.status_var.set(f'Playing preview for "{item.get("trackName", "")}"')

    def open_itunes(self):
        item = self.get_selected_item()
        if not item:
            return
        url = item.get("trackViewUrl") or item.get("collectionViewUrl")
        if not url:
            messagebox.showinfo("No link", "No iTunes/Apple Music link available for this track.")
            return
        webbrowser.open_new_tab(url)
        self.status_var.set(f'Opened iTunes page for "{item.get("trackName", "")}"')

    def open_youtube_spotify(self):
        item = self.get_selected_item()
        if not item:
            return
        title = item.get("trackName", "")
        artist = item.get("artistName", "")
        query = urllib.parse.quote_plus(f"{title} {artist}")
        yt = f"https://www.youtube.com/results?search_query={query}"
        sp = f"https://open.spotify.com/search/{query}"
        webbrowser.open_new_tab(yt)
        webbrowser.open_new_tab(sp)
        self.status_var.set(f'Opened YouTube and Spotify searches for "{title}"')


if __name__ == "__main__":
    app = MoodITunesApp()
    app.mainloop()