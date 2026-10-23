"""A persistent page stack for sidebar navigation, without a hidden tab strip."""
import customtkinter as ctk


class SectionStack(ctk.CTkFrame):
    """Keep all page widgets alive and give the selected page the full body."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._pages = {}
        self._current = ""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def add(self, name):
        if name in self._pages:
            raise ValueError(f"Duplicate section: {name}")
        page = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._pages[name] = page
        if not self._current:
            self.set(name)
        return page

    def tab(self, name):
        return self._pages[name]

    def set(self, name):
        page = self._pages[name]
        if self._current and self._current != name:
            self._pages[self._current].grid_remove()
        page.grid(row=0, column=0, sticky="nsew")
        self._current = name

    def get(self):
        return self._current
