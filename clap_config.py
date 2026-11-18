"""
clap_config.py - Fenêtre de réglage de clap_launcher.py (écrit config.json).

Lancer :  pythonw clap_config.py   (ou le raccourci « Runner - réglages » du Bureau,
          créé automatiquement à la première ouverture)
Les fichiers audio proposés sont ceux du dossier du script et de son sous-dossier « musiques ».
"""

import colorsys
import ctypes
import json
import os
import re
import urllib.parse
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import clap_launcher as cl
except ImportError as e:                         # souvent après une mise à jour de Python
    racine = tk.Tk()
    racine.withdraw()
    messagebox.showerror("Runner", f"Bibliothèque Python manquante : {e.name}\n\nDans un terminal, lance :\n"
                                   "pip install -U sounddevice numpy soundfile edge-tts")
    sys.exit(1)

# Applis proposées dans le menu (seules celles trouvées sur le PC apparaissent)
APPS_CONNUES = {
    "VS Code": [r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
                r"%ProgramFiles%\Microsoft VS Code\Code.exe"],
    "Chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
    "Firefox": [r"%ProgramFiles%\Mozilla Firefox\firefox.exe"],
    "Edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"],
    "Discord": [r"%LOCALAPPDATA%\Discord\app-*\Discord.exe"],
    "Spotify": [r"%APPDATA%\Spotify\Spotify.exe"],
    "Obsidian": [r"%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe",
                 r"%LOCALAPPDATA%\Obsidian\Obsidian.exe"],
    "Steam": [r"%ProgramFiles(x86)%\Steam\steam.exe"],
    "Visual Studio": [r"%ProgramFiles%\Microsoft Visual Studio\*\*\Common7\IDE\devenv.exe"],
    "Unreal Engine": [r"%ProgramFiles%\Epic Games\UE_5*\Engine\Binaries\Win64\UnrealEditor.exe"],
    "Bloc-notes": [r"%WINDIR%\System32\notepad.exe"],
}
CONNUES = {nom: p for nom, pats in APPS_CONNUES.items()
           for p in [next((p for p in pats if cl.chemin(p)), None)] if p}
AUTRE, AUCUNE, PARCOURIR = "Autre…", "(aucune)", "Parcourir…"
SORTIE_AUTO = "Auto (sortie Windows actuelle)"
PYTHON = os.path.join(os.path.dirname(sys.executable), "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable


# Thème sombre (nuances de gris, accent orangé discret)
FOND, SURFACE, CHAMP, BORDURE = "#1f1e1d", "#262624", "#30302e", "#45443f"
FONCE = "#4a4944"                        # contour des champs, menus et boutons
TEXTE, DISCRET, ACCENT = "#ecebe6", "#9c9a92", "#d97757"
ETEINT = "#65635d"                       # réglage grisé (sans effet dans le mode choisi)
POLICE = ("Segoe UI", 12)


def appliquer_theme(racine):
    racine.configure(bg=FOND)
    racine.option_add("*Font", POLICE)
    racine.option_add("*TCombobox*Listbox.background", CHAMP)
    racine.option_add("*TCombobox*Listbox.foreground", TEXTE)
    racine.option_add("*TCombobox*Listbox.selectBackground", BORDURE)
    racine.option_add("*TCombobox*Listbox.selectForeground", TEXTE)
    racine.option_add("*TCombobox*Listbox.font", POLICE)
    racine.option_add("*TCombobox*Listbox.borderWidth", 0)
    st = ttk.Style(racine)
    st.theme_use("clam")
    st.configure(".", background=SURFACE, foreground=TEXTE, font=POLICE, bordercolor=FONCE,
                 lightcolor=CHAMP, darkcolor=CHAMP, troughcolor=CHAMP, focuscolor=SURFACE,
                 fieldbackground=CHAMP, selectbackground=BORDURE, selectforeground=TEXTE,
                 insertcolor=TEXTE, arrowcolor=DISCRET)
    st.configure("Fond.TFrame", background=FOND)
    st.configure("Fond.TLabel", background=FOND, foreground=DISCRET)
    st.configure("Discret.TLabel", foreground=DISCRET)
    st.configure("Titre.TLabel", foreground=DISCRET, font=(POLICE[0], 11))

    st.configure("TButton", background=CHAMP, padding=(16, 8), borderwidth=1, relief="flat",
                 bordercolor=FONCE, lightcolor=CHAMP, darkcolor=CHAMP)
    st.map("TButton", background=[("pressed", FOND), ("active", BORDURE)],
           foreground=[("disabled", ETEINT)],
           lightcolor=[("active", BORDURE)], darkcolor=[("active", BORDURE)])
    st.configure("Accent.TButton", background=ACCENT, foreground=FOND, bordercolor=ACCENT,
                 lightcolor=ACCENT, darkcolor=ACCENT)
    st.map("Accent.TButton", background=[("pressed", "#b85f42"), ("active", "#e08a6d")],
           lightcolor=[("active", "#e08a6d")], darkcolor=[("active", "#e08a6d")])
    for w in ("TEntry", "TSpinbox"):
        st.configure(w, padding=6, relief="flat", bordercolor=FONCE, lightcolor=CHAMP, darkcolor=CHAMP)
        st.map(w, bordercolor=[("focus", FONCE)], lightcolor=[("focus", CHAMP)],
               darkcolor=[("focus", CHAMP)], foreground=[("disabled", ETEINT)],
               fieldbackground=[("disabled", SURFACE)])
    st.configure("TSpinbox", arrowsize=12, background=CHAMP)

    fleche = tk.PhotoImage(master=racine, width=11, height=7)
    for x in range(11):
        y = min(x, 10 - x)
        for dy in (0, 1):
            if y + dy < 7:
                fleche.put(DISCRET, (x, y + dy))
    racine._fleche = fleche
    st.element_create("Plat.fleche", "image", fleche, sticky="", padding=(6, 0, 12, 0))
    st.layout("TCombobox", [("Combobox.field", {"sticky": "nswe", "children": [
        ("Plat.fleche", {"side": "right", "sticky": ""}),
        ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [
            ("Combobox.textarea", {"sticky": "nswe"})]})]})])
    st.configure("TCombobox", padding=(10, 6, 0, 6), borderwidth=0, bordercolor=CHAMP,
                 lightcolor=CHAMP, darkcolor=CHAMP)
    st.map("TCombobox", fieldbackground=[("disabled", SURFACE), ("readonly", CHAMP)],
           foreground=[("disabled", ETEINT), ("readonly", TEXTE)],
           bordercolor=[("focus", CHAMP)], lightcolor=[("focus", CHAMP)], darkcolor=[("focus", CHAMP)])
    st.configure("TSeparator", background=BORDURE)
    st.configure("Vertical.TScrollbar", background=CHAMP, troughcolor=CHAMP, bordercolor=CHAMP,
                 lightcolor=CHAMP, darkcolor=CHAMP, arrowcolor=DISCRET, gripcount=0)
    st.map("Vertical.TScrollbar", background=[("active", BORDURE)])

    st.configure("Nav.TFrame", background=FOND)
    st.configure("Nav.TButton", background=FOND, foreground=DISCRET, anchor="w", padding=(18, 11),
                 borderwidth=0, bordercolor=FOND, lightcolor=FOND, darkcolor=FOND, font=(POLICE[0], 13))
    st.map("Nav.TButton", background=[("active", CHAMP)], foreground=[("active", TEXTE)],
           lightcolor=[("active", CHAMP)], darkcolor=[("active", CHAMP)])
    st.configure("NavSel.TButton", background=SURFACE, foreground=TEXTE, anchor="w", padding=(18, 11),
                 borderwidth=0, bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE,
                 font=(POLICE[0], 13))
    st.map("NavSel.TButton", background=[("active", SURFACE)])


def barre_titre_sombre(racine):
    """Barre de titre de la couleur du fond (Windows 11), ou au moins sombre (Windows 10)."""
    try:
        racine.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(racine.winfo_id())
        regler = ctypes.windll.dwmapi.DwmSetWindowAttribute

        def couleur(hexa):                   # format COLORREF : 0x00BBGGRR
            r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
            return r | g << 8 | b << 16

        for attribut, valeur in ((20, 1), (19, 1),                       # mode sombre
                                 (35, couleur(FOND)), (34, couleur(FOND)),  # barre + bordure
                                 (36, couleur(TEXTE))):                   # texte du titre
            regler(hwnd, attribut, ctypes.byref(ctypes.c_int(valeur)), 4)
        racine.withdraw()                    # force Windows 10 à redessiner la barre
        racine.deiconify()
    except Exception:
        pass


class BoutonIcone(tk.Canvas):
    """Petit bouton carré avec un symbole dessiné : « lecture » (triangle) ou « stop » (carré)."""

    def __init__(self, parent, symbole, commande, taille=34):
        super().__init__(parent, width=taille, height=taille, bg=SURFACE, highlightthickness=0,
                         cursor="hand2")
        self.symbole, self.commande, self.t = symbole, commande, taille
        self.bind("<Button-1>", lambda e: self.commande())
        self.bind("<Enter>", lambda e: self.dessiner(True))
        self.bind("<Leave>", lambda e: self.dessiner(False))
        self.dessiner(False)

    def dessiner(self, survol):
        t = self.t
        self.delete("all")
        arrondi(self, 1, 1, t - 1, t - 1, 7, fill=BORDURE if survol else CHAMP, outline=FONCE)
        couleur = ACCENT if survol else TEXTE
        if self.symbole == "lecture":
            self.create_polygon(t * .36, t * .26, t * .36, t * .74, t * .76, t * .5, fill=couleur, outline="")
        else:
            self.create_rectangle(t * .34, t * .34, t * .66, t * .66, fill=couleur, outline="")


class Curseur(tk.Frame):
    """Curseur dessiné : rail fin, partie remplie orange, gros bouton rond, valeur à droite."""

    def __init__(self, parent, variable, mini, maxi, pas=1, longueur=320, unite=""):
        super().__init__(parent, bg=SURFACE)
        self.var, self.mini, self.maxi, self.pas, self.L = variable, mini, maxi, pas, longueur
        self.unite = f" {unite}" if unite else ""
        self.actif = True
        self.decimales = 0 if pas >= 1 else len(f"{pas:g}".split(".")[1])
        self.c = tk.Canvas(self, width=longueur + 24, height=30, bg=SURFACE, highlightthickness=0,
                           cursor="hand2")
        self.c.pack(side="left")
        self.valeur = tk.Label(self, bg=SURFACE, fg=TEXTE, font=POLICE, width=8, anchor="w")
        self.valeur.pack(side="left", padx=(10, 0))
        for evt in ("<Button-1>", "<B1-Motion>"):
            self.c.bind(evt, lambda e: self.aller(e.x))
        self.c.bind("<MouseWheel>", lambda e: self.regler(self.lire() + (self.pas if e.delta > 0 else -self.pas)))
        variable.trace_add("write", lambda *_: self.dessiner())
        self.dessiner()

    def lire(self):
        try:
            return float(self.var.get())
        except (tk.TclError, ValueError):
            return self.mini

    def activer(self, actif):
        self.actif = actif
        self.c.configure(cursor="hand2" if actif else "")
        self.dessiner()

    def regler(self, v):
        if not self.actif:
            return
        v = min(self.maxi, max(self.mini, round(v / self.pas) * self.pas))
        self.var.set(int(round(v)) if self.decimales == 0 else round(v, self.decimales))

    def aller(self, x):
        t = min(1, max(0, (x - 12) / self.L))
        self.regler(self.mini + t * (self.maxi - self.mini))

    def dessiner(self):
        v = self.lire()
        t = (v - self.mini) / ((self.maxi - self.mini) or 1)
        x, y = 12 + t * self.L, 15
        c = self.c
        c.delete("all")
        c.create_line(12, y, 12 + self.L, y, fill=CHAMP, width=6, capstyle="round")
        c.create_line(12, y, x, y, fill=ACCENT if self.actif else BORDURE, width=6, capstyle="round")
        c.create_oval(x - 9, y - 9, x + 9, y + 9, fill=TEXTE if self.actif else ETEINT, outline=FONCE, width=2)
        self.valeur.configure(text=f"{v:.{self.decimales}f}{self.unite}", fg=TEXTE if self.actif else ETEINT)


def arrondi(c, x0, y0, x1, y1, r, **options):
    """Rectangle aux coins arrondis sur un Canvas."""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **options)


class Case(tk.Frame):
    """Grande case à cocher dessinée (les cases ttk sont minuscules)."""

    def __init__(self, parent, text, variable):
        super().__init__(parent, bg=SURFACE, cursor="hand2")
        self.var, self.actif = variable, True
        self.c = tk.Canvas(self, width=26, height=26, bg=SURFACE, highlightthickness=0, cursor="hand2")
        self.c.pack(side="left")
        self.etiquette = tk.Label(self, text=text, bg=SURFACE, fg=TEXTE, font=POLICE, cursor="hand2")
        self.etiquette.pack(side="left", padx=(10, 0))
        for w in (self, self.c, self.etiquette):
            w.bind("<Button-1>", lambda e: self.actif and self.var.set(not self.var.get()))
        variable.trace_add("write", lambda *_: self.dessiner())
        self.dessiner()

    def activer(self, actif):
        self.actif = actif
        for w in (self, self.c, self.etiquette):
            w.configure(cursor="hand2" if actif else "")
        self.etiquette.configure(fg=TEXTE if actif else ETEINT)
        self.dessiner()

    def dessiner(self):
        c = self.c
        c.delete("all")
        if self.var.get():
            teinte = ACCENT if self.actif else BORDURE
            arrondi(c, 2, 2, 24, 24, 7, fill=teinte, outline=teinte)
            c.create_line(7.5, 13.5, 11.5, 17.5, 18.5, 9, fill=FOND, width=2.6,
                          capstyle="round", joinstyle="round")
        else:
            arrondi(c, 2, 2, 24, 24, 7, fill=CHAMP, outline=BORDURE, width=1.5)


class MenuDeroulant(tk.Frame):
    """Menu déroulant avec bordure dessinée par un cadre d'1 px (orange quand la liste est ouverte)."""

    def __init__(self, parent, **options):
        super().__init__(parent, bg=FONCE)
        options.setdefault("state", "readonly")
        avant_ouverture = options.pop("postcommand", None)

        def ouverture():
            self.configure(bg=ACCENT)
            if avant_ouverture:
                avant_ouverture()

        self.combo = ttk.Combobox(self, postcommand=ouverture, **options)
        self.combo.pack(padx=1, pady=1)
        liste = self.combo.tk.call("ttk::combobox::PopdownWindow", self.combo)
        self.combo.tk.call("bind", liste, "<Unmap>", self.register(lambda: self.configure(bg=FONCE)))

    def bind(self, *args, **kw):
        return self.combo.bind(*args, **kw)

    def activer(self, actif):
        self.combo.configure(state="readonly" if actif else "disabled")

    def __setitem__(self, cle, valeur):
        self.combo[cle] = valeur


class Bulle(tk.Toplevel):
    """Petite fenêtre flottante au thème, sans barre de titre. Clic à côté = fermer en validant,
    Échap = fermer sans valider ; 'a_la_fermeture(valider)' est appelé dans les deux cas."""

    def __init__(self, ancre, x, y, a_la_fermeture=None):
        super().__init__(ancre)
        self.overrideredirect(True)
        self.configure(bg=BORDURE)
        self.corps = tk.Frame(self, bg=CHAMP, padx=16, pady=14)
        self.corps.pack(padx=1, pady=1)
        self.a_la_fermeture = a_la_fermeture
        self.bind("<Button-1>", self._clic, add="+")
        self.bind("<Escape>", lambda e: self.fermer(False))
        self.geometry(f"+{x}+{y}")

    def _clic(self, e):
        x, y = e.x_root - self.winfo_rootx(), e.y_root - self.winfo_rooty()
        if not (0 <= x < self.winfo_width() and 0 <= y < self.winfo_height()):
            self.fermer(True)

    def montrer(self, focus=None):
        """À appeler une fois le contenu construit : capture le clavier et la souris."""
        self.focus_force()
        if focus:
            focus.focus_set()
        self.grab_set()

    def fermer(self, valider=True):
        if self.a_la_fermeture:
            self.a_la_fermeture(valider)
        self.grab_release()
        self.destroy()


class SelecteurCouleur:
    """Sélecteur de couleur au thème de la fenêtre : carré saturation/luminosité, barre de
    teinte, couleurs prédéfinies et code hexadécimal. Entrée/OK/clic à côté = valider, Échap = annuler."""
    L, H, BARRE = 260, 170, 16
    PREDEFINIES = ["#ff0000", "#ff6a00", "#ffc800", "#00ff3c", "#00e5ff", "#0050ff",
                   "#8a2be2", "#ff00b4", "#ffffff", "#ffd29a"]

    def __init__(self, ancre, couleur, valider):
        import numpy as np
        self.np, self.valider = np, valider
        r, g, b = (int(couleur[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self.haut = haut = Bulle(ancre, ancre.winfo_rootx(), ancre.winfo_rooty() + ancre.winfo_height() + 6,
                                 lambda valider: valider and self.valider(self.couleur()))
        corps = haut.corps

        self.carre = tk.Canvas(corps, width=self.L, height=self.H, bg=CHAMP, highlightthickness=0,
                               cursor="crosshair")
        self.carre.pack()
        self.img_carre = tk.PhotoImage(master=haut, width=self.L, height=self.H)
        self.carre.create_image(0, 0, image=self.img_carre, anchor="nw")
        self.repere = self.carre.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        for evt in ("<Button-1>", "<B1-Motion>"):
            self.carre.bind(evt, self.clic_carre)

        self.barre = tk.Canvas(corps, width=self.L, height=self.BARRE, bg=CHAMP, highlightthickness=0,
                               cursor="hand2")
        self.barre.pack(pady=(10, 0))
        self.img_barre = tk.PhotoImage(master=haut, width=self.L, height=self.BARRE)
        teintes = self.vers_hex(np.linspace(0, 1, self.L), 1.0, 1.0)
        ligne = "{" + " ".join(teintes) + "}"
        self.img_barre.put(" ".join([ligne] * self.BARRE))
        self.barre.create_image(0, 0, image=self.img_barre, anchor="nw")
        self.curseur_teinte = self.barre.create_rectangle(0, 0, 0, 0, outline="#ffffff", width=2)
        for evt in ("<Button-1>", "<B1-Motion>"):
            self.barre.bind(evt, self.clic_barre)

        palette = tk.Frame(corps, bg=CHAMP)
        palette.pack(fill="x", pady=(12, 0))
        for c in self.PREDEFINIES:
            p = tk.Canvas(palette, width=22, height=22, bg=CHAMP, highlightthickness=0, cursor="hand2")
            arrondi(p, 1, 1, 21, 21, 6, fill=c, outline=FONCE)
            p.bind("<Button-1>", lambda e, c=c: self.depuis_hex(c))
            p.pack(side="left", padx=(0, 4))

        bas = tk.Frame(corps, bg=CHAMP)
        bas.pack(fill="x", pady=(12, 0))
        self.apercu = tk.Canvas(bas, width=34, height=30, bg=CHAMP, highlightthickness=0)
        self.apercu.pack(side="left")
        self.code = tk.StringVar()
        champ = ttk.Entry(bas, textvariable=self.code, width=9)
        champ.pack(side="left", padx=10)
        champ.bind("<Return>", lambda e: (self.depuis_hex(self.code.get()), haut.fermer(True)))
        champ.bind("<FocusOut>", lambda e: self.depuis_hex(self.code.get()))
        ttk.Button(bas, text="OK", style="Accent.TButton", command=lambda: haut.fermer(True)).pack(side="right")
        self.peindre_carre()
        self.maj()
        haut.montrer()

    def vers_hex(self, h, s, v):
        """Conversion HSV -> '#rrggbb' sur des tableaux numpy (rapide pour toute l'image)."""
        np = self.np
        h, s, v = np.broadcast_arrays(np.asarray(h, float), np.asarray(s, float), np.asarray(v, float))
        i = (h * 6).astype(int) % 6
        f = h * 6 - np.floor(h * 6)
        p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
        r = np.choose(i, [v, q, p, p, t, v])
        g = np.choose(i, [t, v, v, q, p, p])
        b = np.choose(i, [p, p, t, v, v, q])
        rgb = (np.stack([r, g, b], -1) * 255).round().astype(int)
        return ["#%02x%02x%02x" % tuple(x) for x in rgb.reshape(-1, 3)]

    def peindre_carre(self):
        np = self.np
        s = np.linspace(0, 1, self.L)[None, :]
        v = np.linspace(1, 0, self.H)[:, None]
        pixels = np.array(self.vers_hex(self.h, s, v)).reshape(self.H, self.L)
        self.img_carre.put(" ".join("{" + " ".join(ligne) + "}" for ligne in pixels))

    def couleur(self):
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

    def maj(self):
        x, y = self.s * self.L, (1 - self.v) * self.H
        self.carre.coords(self.repere, x - 7, y - 7, x + 7, y + 7)
        hx = self.h * self.L
        self.barre.coords(self.curseur_teinte, hx - 3, 1, hx + 3, self.BARRE - 1)
        self.apercu.delete("all")
        arrondi(self.apercu, 1, 1, 33, 29, 7, fill=self.couleur(), outline=FONCE)
        self.code.set(self.couleur())

    def clic_carre(self, e):
        self.s = min(1, max(0, e.x / self.L))
        self.v = min(1, max(0, 1 - e.y / self.H))
        self.maj()

    def clic_barre(self, e):
        self.h = min(0.999, max(0, e.x / self.L))
        self.peindre_carre()
        self.maj()

    def depuis_hex(self, texte):
        texte = texte.strip()
        if not texte.startswith("#"):
            texte = "#" + texte
        if re.fullmatch(r"#[0-9a-fA-F]{6}", texte):
            r, g, b = (int(texte[i:i + 2], 16) / 255 for i in (1, 3, 5))
            h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
            if self.s > 0:                       # pour un gris, la teinte n'a pas de sens : on la garde
                self.h = h
            self.peindre_carre()
            self.maj()


def se_chevauchent(z1, z2):
    (a0, a1), (b0, b1) = cl.ZONES[z1], cl.ZONES[z2]
    return a0 < b1 - 0.01 and b0 < a1 - 0.01


def dessiner_dispo(c, x, y, w, h, zones, couleur, tag_zone=True):
    """Dessine un écran miniature découpé selon 'zones' ; couleur(zone) -> (remplissage, contour)."""
    ids = {}
    for z in zones:
        f0, f1 = cl.ZONES[z]
        x0 = x + f0 * w + (2 if f0 > 0 else 0)
        x1 = x + f1 * w - (2 if f1 < 1 else 0)
        rempli, contour = couleur(z)
        ids[z] = arrondi(c, x0, y, x1, y + h, 5, fill=rempli, outline=contour, width=2,
                         tags=(z,) if tag_zone else ())
    return ids


class SelecteurZone:
    """Miniature de la position choisie ; au clic, menu des dispositions façon Windows 11.
    Les emplacements déjà pris par une autre appli sur le même écran sont grisés."""

    def __init__(self, parent, zone, ecran, zones_prises):
        self.zone, self.ecran, self.zones_prises = zone, ecran, zones_prises
        self.c = tk.Canvas(parent, width=70, height=40, bg=SURFACE, highlightthickness=0, cursor="hand2")
        self.c.bind("<Button-1>", lambda e: self.ouvrir())
        zone.trace_add("write", lambda *_: self.dessiner())
        self.dessiner()

    def grid(self, **kw):
        self.c.grid(**kw)

    def dessiner(self):
        self.c.delete("all")
        arrondi(self.c, 1, 1, 69, 39, 6, fill=CHAMP, outline=FONCE)
        dessiner_dispo(self.c, 6, 6, 58, 28, [self.zone.get()], lambda z: (ACCENT, ACCENT), False)

    def ouvrir(self):
        prises = self.zones_prises()
        haut = Bulle(self.c, self.c.winfo_rootx(), self.c.winfo_rooty() + 46)
        cadre = haut.corps
        tk.Label(cadre, text=f"Position sur l'écran {self.ecran.get()}", bg=CHAMP, fg=DISCRET,
                 font=(POLICE[0], 11)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        def etat(z):
            if any(se_chevauchent(z, p) for p in prises):
                return "#2a2a28", "#2a2a28"                       # pris : grisé
            return (ACCENT, ACCENT) if z == self.zone.get() else (BORDURE, BORDURE)

        for i, dispo in enumerate(cl.DISPOSITIONS):
            cv = tk.Canvas(cadre, width=132, height=82, bg=CHAMP, highlightthickness=0)
            cv.grid(row=1 + i // 3, column=i % 3, padx=7, pady=7)
            ids = dessiner_dispo(cv, 4, 4, 124, 74, dispo, etat)
            for z, ident in ids.items():
                if any(se_chevauchent(z, p) for p in prises):
                    continue
                cv.tag_bind(ident, "<Enter>", lambda e, cv=cv, i=ident: (
                    cv.itemconfigure(i, fill="#e08a6d", outline="#e08a6d"), cv.configure(cursor="hand2")))
                cv.tag_bind(ident, "<Leave>", lambda e, cv=cv, i=ident, z=z: (
                    cv.itemconfigure(i, fill=etat(z)[0], outline=etat(z)[1]), cv.configure(cursor="")))
                cv.tag_bind(ident, "<Button-1>", lambda e, z=z: (self.zone.set(z), haut.fermer()))
        haut.montrer()


def nom_app(exe):
    for nom, pat in CONNUES.items():
        if exe == pat or cl.chemin(exe) == cl.chemin(pat):
            return nom
    return os.path.splitext(os.path.basename(exe))[0] if exe else ""


def nombre(var, defaut=0.0):
    try:
        return float(var.get())
    except (tk.TclError, ValueError):
        return defaut


def en_fond(fonction):
    """Exécute une fonction de test sans bloquer la fenêtre."""
    threading.Thread(target=fonction, daemon=True).start()


def domaine(url):
    nom = urllib.parse.urlparse(url).netloc or url
    return nom[4:] if nom.startswith("www.") else nom


def normaliser_url(url):
    url = url.strip().replace(" ", "")
    if url and not url.startswith("-") and not re.match(r"^[a-zA-Z][\w+.-]*://", url):
        url = "https://" + url
    return url


class EditeurOnglets:
    """Case « Arguments » d'un navigateur : résumé des onglets ; au clic, éditeur une ligne par onglet."""

    def __init__(self, parent, args):
        self.args = args
        self.cadre = tk.Frame(parent, bg=FONCE)
        self.etiquette = tk.Label(self.cadre, bg=CHAMP, fg=TEXTE, font=POLICE, anchor="w", width=38,
                                  padx=10, pady=5, cursor="hand2")
        self.etiquette.pack(padx=1, pady=1)
        self.etiquette.bind("<Button-1>", lambda e: self.ouvrir())
        args.trace_add("write", lambda *_: self.resumer())
        self.resumer()

    def urls(self):
        return self.args.get().split()

    def resumer(self):
        urls = self.urls()
        if urls:
            texte = f"{len(urls)} onglet{'s' if len(urls) > 1 else ''} : " + ", ".join(map(domaine, urls))
        else:
            texte = "Nouvelle fenêtre vide"
        self.etiquette.configure(text=texte if len(texte) <= 42 else texte[:41] + "…")

    def ouvrir(self):
        self.cadre.configure(bg=ACCENT)
        champs = [tk.StringVar(value=u) for u in self.urls()] or [tk.StringVar()]

        def enregistrer(_valider):                # Échap comme clic à côté : on garde la saisie
            self.args.set(" ".join(normaliser_url(v.get()) for v in champs if v.get().strip()))
            self.cadre.configure(bg=FONCE)

        haut = Bulle(self.cadre, self.cadre.winfo_rootx(),
                     self.cadre.winfo_rooty() + self.cadre.winfo_height() + 4, enregistrer)
        corps = haut.corps
        tk.Label(corps, text="Onglets de la fenêtre", bg=CHAMP, fg=DISCRET,
                 font=(POLICE[0], 11)).pack(anchor="w", pady=(0, 8))
        liste = tk.Frame(corps, bg=CHAMP)
        liste.pack(fill="x")

        def construire():
            for w in liste.winfo_children():
                w.destroy()
            dernier = None
            for i, v in enumerate(champs):
                dernier = ttk.Entry(liste, textvariable=v, width=46)
                dernier.grid(row=i, column=0, pady=4)
                dernier.bind("<Return>", lambda e: haut.fermer())
                ttk.Button(liste, text="✕", width=3,
                           command=lambda v=v: (champs.remove(v), construire())).grid(
                    row=i, column=1, padx=(8, 0))
            return dernier

        def ajouter():
            champs.append(tk.StringVar())
            construire().focus_set()

        boutons = tk.Frame(corps, bg=CHAMP)
        boutons.pack(fill="x", pady=(12, 0))
        ttk.Button(boutons, text="+ Ajouter un onglet", command=ajouter).pack(side="left")
        ttk.Button(boutons, text="OK", style="Accent.TButton", command=haut.fermer).pack(side="right")
        haut.montrer(construire())


class LigneApp:
    """Une ligne du tableau des apps."""

    def __init__(self, parent, rang, app, supprimer, zones_prises):
        self.exe = app.get("exe", "")
        self.nom = tk.StringVar(value=nom_app(self.exe))
        self.args = tk.StringVar(value=app.get("args", ""))
        self.ecran = tk.StringVar(value=app.get("ecran", "principal"))
        self.zone = tk.StringVar(value=app.get("zone", "plein"))

        menu = MenuDeroulant(parent, textvariable=self.nom, state="readonly", width=16,
                            values=list(CONNUES) + [AUTRE])
        menu.bind("<<ComboboxSelected>>", self.choisir)
        self.champ = ttk.Entry(parent, textvariable=self.args, width=40)
        self.champ.bind("<FocusOut>", self.verifier_args)
        self.onglets = EditeurOnglets(parent, self.args)
        ecran = MenuDeroulant(parent, textvariable=self.ecran, values=cl.ECRANS, state="readonly", width=12)
        position = SelecteurZone(parent, self.zone, self.ecran, lambda: zones_prises(self))
        bouton = ttk.Button(parent, text="✕", width=3, command=lambda: supprimer(self))
        self.widgets = [menu, self.champ, ecran, position.c, bouton]
        for col, w in enumerate(self.widgets):
            w.grid(row=rang, column=col, padx=(0, 22), pady=13, sticky="w")
        self.onglets.cadre.grid(row=rang, column=1, padx=(0, 22), pady=13, sticky="w")
        self.widgets.append(self.onglets.cadre)
        self.adapter()

    def navigateur(self):
        exe = cl.chemin(self.exe) or self.exe.split("|")[0]
        return os.path.basename(exe).lower() in cl.NAVIGATEURS

    def adapter(self):
        """Navigateur : éditeur d'onglets ; autre appli : champ d'arguments libre."""
        if self.navigateur():
            self.champ.grid_remove()
            self.onglets.cadre.grid()
        else:
            self.onglets.cadre.grid_remove()
            self.champ.grid()

    def detruire(self):
        for w in self.widgets:
            w.destroy()

    def choisir(self, _):
        if self.nom.get() == AUTRE:
            f = filedialog.askopenfilename(title="Choisir un programme",
                                           filetypes=[("Programmes", "*.exe")])
            if f:
                self.exe = os.path.normpath(f)
            self.nom.set(nom_app(self.exe))
        else:
            self.exe = CONNUES[self.nom.get()]
        self.adapter()

    def verifier_args(self, _=None):
        """Un chemin de .exe collé dans « Arguments » devient le programme de la ligne."""
        texte = self.args.get().strip().strip('"')
        if texte.lower().endswith(".exe"):
            self.exe = os.path.normpath(texte)
            self.nom.set(nom_app(self.exe))
            self.args.set("")
            self.adapter()

    def valeur(self):
        self.verifier_args()
        return {"exe": self.exe, "args": self.args.get().strip(),
                "ecran": self.ecran.get(), "zone": self.zone.get()}



COMPTES_TYPES = {"Gmail": {"type": "gmail", "nom": "Gmail", "webmail": "https://mail.google.com"},
                 "ENSMA": {"nom": "ENSMA", "serveur": "", "webmail": ""}}


class LigneCompte:
    """Une ligne du tableau des comptes mail. Gmail : bouton « Se connecter avec Google » (OAuth,
    aucun mot de passe) ; autres boîtes : serveur IMAP et mot de passe."""

    def __init__(self, parent, rang, compte, supprimer, fenetre):
        self.fenetre, self.gmail = fenetre, compte.get("type") == "gmail"
        self.nom = tk.StringVar(value=compte.get("nom", ""))
        self.adresse = tk.StringVar(value=compte.get("adresse", ""))
        self.serveur = tk.StringVar(value=compte.get("serveur", ""))
        self.webmail = tk.StringVar(value=compte.get("webmail", ""))
        self.mdp = tk.StringVar()
        if self.gmail:
            adresse = ttk.Label(parent, textvariable=self.adresse, width=26)
            serveur = ttk.Label(parent, text="Connexion Google", style="Discret.TLabel", width=18)
            self.bouton_google = ttk.Button(parent, command=self.connexion_google)
            acces = self.bouton_google
            self.etat_google()
        else:
            adresse = ttk.Entry(parent, textvariable=self.adresse, width=26)
            serveur = ttk.Entry(parent, textvariable=self.serveur, width=18)
            acces = ttk.Frame(parent)
            ttk.Entry(acces, textvariable=self.mdp, width=14, show="•").pack(side="left")
            self.etiquette_mdp = ttk.Label(acces, style="Discret.TLabel", width=11)
            self.etiquette_mdp.pack(side="left", padx=(8, 0))
            self.etat_mdp()
        self.widgets = [ttk.Entry(parent, textvariable=self.nom, width=9), adresse, serveur, acces,
                        ttk.Entry(parent, textvariable=self.webmail, width=24),
                        ttk.Button(parent, text="✕", width=3, command=lambda: supprimer(self))]
        for col, w in enumerate(self.widgets):
            w.grid(row=rang, column=col, padx=(0, 14), pady=6, sticky="w")

    def etat_mdp(self):
        if self.gmail:
            return
        try:
            garde = bool(self.adresse.get().strip()) and cl.lire_mot_de_passe(self.adresse.get()) is not None
        except Exception:
            garde = False
        self.etiquette_mdp.configure(text="✓ enregistré" if garde else "")

    def etat_google(self):
        try:
            connecte = bool(self.adresse.get()) and cl.lire_mot_de_passe(f"google:{self.adresse.get()}") is not None
        except Exception:
            connecte = False
        if not connecte:
            self.adresse.set("(non connecté)" if not self.adresse.get() else self.adresse.get())
        self.bouton_google.configure(text="Déconnecter" if connecte else "Se connecter avec Google")

    def connexion_google(self):
        adresse = self.adresse.get()
        if self.bouton_google.cget("text") == "Déconnecter":
            if messagebox.askyesno("Gmail", f"Déconnecter {adresse} ? Runner ne lira plus cette boîte."):
                en_fond(lambda: (cl.deconnecter_google(adresse), self.fenetre.after(0, self.apres_google, "")))
            return
        if not os.path.exists(cl.FICHIER_GOOGLE) and not self.choisir_fichier_google():
            return
        self.fenetre.status.set("Connexion à Google : termine dans ton navigateur…")

        def connecter():
            try:
                adresse = cl.connecter_google()
                self.fenetre.after(0, self.apres_google, adresse)
                self.fenetre.dire(f"Gmail connecté : {adresse} ✓ (pense à enregistrer)")
            except Exception as e:
                self.fenetre.dire(f"Connexion Google impossible : {e}")
        en_fond(connecter)

    def apres_google(self, adresse):
        self.adresse.set(adresse)
        self.etat_google()

    def choisir_fichier_google(self):
        """Premier usage : le fichier d'ID client OAuth téléchargé depuis Google Cloud."""
        messagebox.showinfo(
            "Connexion Google : préparation (une seule fois)",
            "Runner a besoin d'un « ID client OAuth » Google (gratuit). Dans console.cloud.google.com :\n\n"
            "1. Crée un projet, puis active « Gmail API ».\n"
            "2. Écran de consentement OAuth : type « Externe », puis « Publier l'application » "
            "(sinon il faut se reconnecter tous les 7 jours).\n"
            "3. Identifiants › Créer › ID client OAuth › « Application de bureau » › Télécharger le JSON.\n\n"
            "Choisis maintenant ce fichier JSON. Le détail est dans DOCUMENTATION.md (page Infos).")
        f = filedialog.askopenfilename(title="Fichier d'ID client OAuth Google", filetypes=[("JSON", "*.json")])
        if not f:
            return False
        try:
            with open(f, encoding="utf-8") as src:
                d = json.load(src)
            if "client_id" not in (d.get("installed") or d.get("web") or d):
                raise ValueError("ce fichier ne contient pas d'ID client")
            with open(cl.FICHIER_GOOGLE, "w", encoding="utf-8") as dst:
                json.dump(d, dst, indent=2)
            return True
        except (OSError, ValueError) as e:
            messagebox.showerror("Connexion Google", f"Fichier invalide : {e}")
            return False

    def valeur(self):
        adresse = self.adresse.get().strip()
        v = {"nom": self.nom.get().strip(), "adresse": "" if adresse.startswith("(") else adresse,
             "webmail": normaliser_url(self.webmail.get()), "actif": True}
        if self.gmail:
            v["type"] = "gmail"
        else:
            v["serveur"] = self.serveur.get().strip()
        return v

    def detruire(self):
        for w in self.widgets:
            w.destroy()


class Calibrage(tk.Toplevel):
    """Calibrage guidé : 6 claps, puis 8 s de parole ; Runner calcule des seuils qui gardent
    les claps et rejettent la voix. Le Runner en arrière-plan est en pause pendant ce temps."""
    PHRASE = ("« Bonjour Runner, je teste la détection des claps. Aujourd'hui j'ai cours à huit heures, "
              "puis je travaille sur mon projet. » Tu peux aussi tousser ou poser un objet sur le bureau.")

    def __init__(self, fenetre):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.title("Calibrage de la détection")
        self.configure(bg=SURFACE)
        self.resizable(False, False)
        self.transient(fenetre)
        self.corps = tk.Frame(self, bg=SURFACE, padx=34, pady=28)
        self.corps.pack()
        self.titre = tk.Label(self.corps, bg=SURFACE, fg=TEXTE, font=(POLICE[0], 16), justify="left")
        self.titre.pack(anchor="w")
        self.texte = tk.Label(self.corps, bg=SURFACE, fg=DISCRET, font=POLICE, justify="left", wraplength=620)
        self.texte.pack(anchor="w", pady=(10, 14))
        self.barre = tk.Canvas(self.corps, width=620, height=10, bg=SURFACE, highlightthickness=0)
        self.barre.pack(anchor="w")
        self.boutons = tk.Frame(self.corps, bg=SURFACE)
        self.boutons.pack(anchor="e", pady=(22, 0))
        self.sons_claps = None
        self.protocol("WM_DELETE_WINDOW", self.fermer)
        self.geometry(f"+{fenetre.winfo_rootx() + 160}+{fenetre.winfo_rooty() + 140}")
        barre_titre_sombre(self)
        self.grab_set()
        cl.mettre_les_autres_en_pause()
        self.accueil()

    def ecran(self, titre, texte, boutons):
        self.titre.configure(text=titre)
        self.texte.configure(text=texte)
        self.progression(0)
        for w in self.boutons.winfo_children():
            w.destroy()
        for texte_bouton, commande, accent in boutons:
            ttk.Button(self.boutons, text=texte_bouton, command=commande,
                       style="Accent.TButton" if accent else "TButton").pack(side="left", padx=(8, 0))

    def progression(self, p):
        self.barre.delete("all")
        arrondi(self.barre, 1, 1, 619, 9, 4, fill=CHAMP, outline=CHAMP)
        if p > 0:
            arrondi(self.barre, 1, 1, max(12, 618 * p), 9, 4, fill=ACCENT, outline=ACCENT)

    def accueil(self):
        self.ecran("Calibrer la détection des claps",
                   "Runner va régler la détection pour ton micro, ta pièce et ta façon de taper :\n"
                   "1.  tape 6 fois dans tes mains, environ une fois par seconde ;\n"
                   "2.  parle normalement pendant 8 secondes.\n\n"
                   "Mets-toi à l'endroit d'où tu tapes d'habitude. Le Runner en arrière-plan est en pause "
                   "pendant le calibrage.",
                   [("Annuler", self.fermer, False), ("Commencer", self.etape_claps, True)])

    def enregistrer(self, duree, titre, texte, suite):
        """Compte à rebours + enregistrement dans un fil secondaire, puis suite(sons)."""
        self.ecran(titre, texte, [("Annuler", self.fermer, False)])
        debut, res = time.time(), {}

        def fil():
            try:
                res["sons"] = cl.sons_forts(cl.enregistrer_micro(duree))
            except Exception as e:
                res["erreur"] = e

        threading.Thread(target=fil, daemon=True).start()

        def suivre():
            if not self.winfo_exists():
                return
            if "sons" in res or "erreur" in res:
                if "erreur" in res:
                    self.ecran("Micro indisponible", f"{res['erreur']}", [("Fermer", self.fermer, True)])
                else:
                    suite(res["sons"])
                return
            ecoule = time.time() - debut
            self.progression(min(1, ecoule / duree))
            self.titre.configure(text=f"{titre}   {max(0, duree - ecoule):.0f} s")
            self.after(100, suivre)
        suivre()

    def etape_claps(self):
        self.fenetre.reglages_actuels()                  # micro choisi dans la fenêtre
        self.enregistrer(9, "Tape 6 fois dans tes mains", "Environ une fois par seconde, comme pour lancer Runner.",
                         self.apres_claps)

    def apres_claps(self, sons):
        plus_fort = max((s["vol"] for s in sons), default=0)
        n = sum(s["vol"] >= 0.3 * plus_fort for s in sons) if sons else 0
        if n < 3:
            self.ecran("Pas assez de claps entendus",
                       f"Runner n'a repéré que {n} clap(s). Vérifie le micro choisi (page Détection), "
                       "rapproche-toi ou tape un peu plus fort.",
                       [("Annuler", self.fermer, False), ("Recommencer", self.etape_claps, True)])
            return
        self.sons_claps = sons
        self.ecran(f"{n} claps repérés ✓", "Maintenant, parle normalement pendant 8 secondes. Par exemple :\n\n"
                   + self.PHRASE, [("Annuler", self.fermer, False), ("Je suis prêt", self.etape_parole, True)])

    def etape_parole(self):
        self.enregistrer(8, "Parle normalement", self.PHRASE, self.resultat)

    def resultat(self, sons_parole):
        try:
            reglages, ok, n, faux, total = cl.calibrer(self.sons_claps, sons_parole)
        except ValueError as e:
            self.ecran("Calibrage impossible", str(e), [("Annuler", self.fermer, False),
                                                         ("Recommencer", self.etape_claps, True)])
            return
        self.reglages = reglages
        noms = {"attaque_min": "Attaque min", "decroissance_max": "Décroissance max",
                "brillance_min": "Brillance min", "fond_min": "Au-dessus du bruit de fond",
                "seuil_min": "Volume minimum"}
        lignes = [f"{noms[k]} :  {self.fenetre.det[k].get():g}  →  {v:g}" for k, v in reglages.items()]
        bilan = f"Claps reconnus : {ok} sur {n}.   Sons de ta voix pris pour un clap : {faux} sur {total}."
        if faux or ok < n:
            bilan += ("\n\nLe résultat n'est pas parfait : parle un peu plus loin du micro, tape plus fort ou "
                      "plus près, puis recommence.")
        self.ecran("Résultat du calibrage", bilan + "\n\n" + "\n".join(lignes),
                   [("Annuler", self.fermer, False), ("Recommencer", self.etape_claps, False),
                    ("Appliquer", self.appliquer, True)])

    def appliquer(self):
        for k, v in self.reglages.items():
            self.fenetre.det[k].set(v)
        self.fenetre.status.set("Calibrage appliqué : pense à enregistrer")
        cl.print(f"Calibrage appliqué : {self.reglages}")
        self.fermer()

    def fermer(self):
        cl.reprendre_les_autres()
        self.grab_release()
        self.destroy()


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


class Recap(tk.Tk):
    """Fenêtre de récap au lancement : cours du jour et derniers mails non lus."""

    def __init__(self, fichier):
        super().__init__()
        from datetime import datetime
        with open(fichier, encoding="utf-8") as f:
            d = json.load(f)
        appliquer_theme(self)
        self.configure(bg=SURFACE)
        self.title("Runner — aujourd'hui")
        self.attributes("-topmost", True)
        self.bind("<Escape>", lambda e: self.destroy())
        c = tk.Frame(self, bg=SURFACE, padx=28, pady=22)
        c.pack(fill="both", expand=True)
        maintenant = datetime.now()
        tk.Label(c, text=f"{JOURS[maintenant.weekday()].capitalize()} {maintenant.day} {MOIS[maintenant.month - 1]}",
                 bg=SURFACE, fg=TEXTE, font=(POLICE[0], 17)).pack(anchor="w")

        def section(titre):
            tk.Label(c, text=titre.upper(), bg=SURFACE, fg=DISCRET, font=(POLICE[0], 10, "bold")).pack(
                anchor="w", pady=(18, 6))

        def ligne(texte, couleur=TEXTE, gras=False):
            tk.Label(c, text=texte, bg=SURFACE, fg=couleur, font=(POLICE[0], 12, "bold" if gras else "normal"),
                     justify="left", wraplength=520).pack(anchor="w", pady=1)

        if d.get("agenda"):
            section("Cours")
            if not d["cours"]:
                ligne("Plus de cours aujourd'hui", DISCRET)
            for debut, fin, titre, lieu in d["cours"]:
                debut, fin = datetime.fromisoformat(debut), datetime.fromisoformat(fin)
                ligne(f"{debut:%H:%M} – {fin:%H:%M}   {titre}" + (f"   · {lieu}" if lieu else ""))
        if d.get("mails"):
            section("Mails non lus")
            for nom, boite in d["mails"].items():
                haut = tk.Frame(c, bg=SURFACE)
                haut.pack(anchor="w", fill="x", pady=(6, 2))
                if isinstance(boite, dict):
                    tk.Label(haut, text=f"{nom}  ·  {boite['non_lus']}", bg=SURFACE, fg=TEXTE,
                             font=(POLICE[0], 12, "bold")).pack(side="left")
                else:
                    tk.Label(haut, text=f"{nom}  ·  indisponible", bg=SURFACE, fg="#e0b35a",
                             font=(POLICE[0], 12, "bold")).pack(side="left")
                url = d.get("webmails", {}).get(nom)
                if url:
                    ttk.Button(haut, text="Ouvrir", command=lambda u=url: os.startfile(u)).pack(side="right")
                if isinstance(boite, dict):
                    for expediteur, objet in boite["derniers"]:
                        texte = f"{expediteur} — {objet}"
                        ligne(texte if len(texte) <= 70 else texte[:69] + "…", DISCRET)
                else:
                    ligne(boite, DISCRET)
        ttk.Button(c, text="Fermer", command=self.destroy).pack(anchor="e", pady=(20, 0))
        self.update_idletasks()
        self.geometry(f"+{self.winfo_screenwidth() - self.winfo_reqwidth() - 40}+40")
        barre_titre_sombre(self)


class Fenetre(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Runner — réglages")
        appliquer_theme(self)
        larg, haut = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = max(1200, int(larg * 0.72)), max(820, int(haut * 0.8))
        w, h = min(w, larg - 40), min(h, haut - 80)
        self.geometry(f"{w}x{h}+{(larg - w) // 2}+{max(0, (haut - h) // 2 - 20)}")
        self.minsize(1100, 760)
        self.cfg = cl.charger_config()
        self.status = tk.StringVar(value="")
        if cl.ALERTES_CONFIG:
            self.after(300, lambda: messagebox.showwarning("Réglages", "\n".join(cl.ALERTES_CONFIG)))
        self.tests = set()                       # tests en cours (le bouton Stop n'apparaît qu'alors)
        self.processus_test = None
        self.apercu = None
        self.lecteur_voix = None

        # Menu à gauche
        nav = ttk.Frame(self, style="Nav.TFrame", padding=(14, 22))
        nav.pack(side="left", fill="y")
        ttk.Frame(nav, style="Nav.TFrame", height=22).pack()
        droite = ttk.Frame(self, style="Fond.TFrame")
        droite.pack(side="left", fill="both", expand=True)

        # Grand cadre arrondi qui contient les pages
        toile = tk.Canvas(droite, bg=FOND, highlightthickness=0)
        toile.pack(fill="both", expand=True, padx=(0, 16), pady=(16, 0))
        interieur = ttk.Frame(toile)
        fenetre_interieure = toile.create_window(10, 10, window=interieur, anchor="nw")

        def redessiner(e):
            toile.delete("cadre")
            arrondi(toile, 1, 1, e.width - 2, e.height - 2, 16, fill=SURFACE, outline=BORDURE,
                    width=1, tags="cadre")
            toile.tag_lower("cadre")
            toile.itemconfigure(fenetre_interieure, width=e.width - 20, height=e.height - 20)

        toile.bind("<Configure>", redessiner)
        interieur.grid_rowconfigure(0, weight=1)
        interieur.grid_columnconfigure(0, weight=1)

        self.pages, self.boutons = {}, {}
        for titre, construire in [("Apps", self.page_apps), ("LED", self.page_leds),
                                  ("Voix", self.page_voix), ("Infos", self.page_infos),
                                  ("Musique", self.page_musique),
                                  ("Détection", self.page_detection), ("Système", self.page_systeme),
                                  ("Journal", self.page_journal)]:
            page = ttk.Frame(interieur, padding=(32, 26))
            page.grid(row=0, column=0, sticky="nsew")
            construire(page)
            self.pages[titre] = page
            self.boutons[titre] = ttk.Button(nav, text=titre, style="Nav.TButton", width=16,
                                             command=lambda t=titre: self.afficher(t))
            self.boutons[titre].pack(fill="x", pady=2)
        self.afficher("Apps")

        # Barre du bas
        bas = ttk.Frame(droite, padding=16, style="Fond.TFrame")
        bas.pack(fill="x")
        ttk.Label(bas, textvariable=self.status, style="Fond.TLabel").pack(side="left")
        ttk.Button(bas, text="Tester tout", style="Accent.TButton", command=self.tester_tout).pack(side="right")
        ttk.Button(bas, text="Enregistrer", command=self.enregistrer).pack(side="right", padx=(0, 8))
        self.bouton_stop = ttk.Button(bas, text="■  Stop", command=self.arreter)

        self.protocol("WM_DELETE_WINDOW", self.fermer)
        barre_titre_sombre(self)
        en_fond(lambda: cl.reparer_raccourcis(bureau=True))   # crée ou répare les raccourcis
        cl.CFG = self.lire()
        en_fond(cl.preparer_voix_en_boucle)
        self.prechargement_auto()

    def afficher(self, titre):
        self.page_actuelle = titre
        self.pages[titre].tkraise()
        if titre == "Journal":
            self.charger_journal(force=True)
        for t, b in self.boutons.items():
            b.configure(style="NavSel.TButton" if t == titre else "Nav.TButton")

    @staticmethod
    def ligne(f, rang, texte, widget):
        etiquette = ttk.Label(f, text=texte)
        etiquette.grid(row=rang, column=0, sticky="w", pady=16, padx=(0, 40))
        widget.grid(row=rang, column=1, sticky="w", pady=16)
        return etiquette

    def dire(self, message):
        """Met à jour la ligne d'état (appelable depuis un fil secondaire) et note dans le journal."""
        self.after(0, self.status.set, message)
        if message:
            cl.print(message)

    # ------------------------------- Pages -------------------------------
    def page_apps(self, f):
        self.cadre_apps = ttk.Frame(f)
        self.cadre_apps.pack(anchor="w", pady=4)
        for col, txt in enumerate(["App", "Arguments / onglets", "Écran", "Position"]):
            ttk.Label(self.cadre_apps, text=txt, style="Titre.TLabel").grid(
                row=0, column=col, padx=(0, 22), pady=(0, 2), sticky="w")
        self.lignes, self.prochain_rang = [], 1
        for app in self.cfg["apps"]:
            self.ajouter_app(app)
        boutons = ttk.Frame(f)
        boutons.pack(anchor="w", pady=(10, 14))
        ttk.Button(boutons, text="+ Ajouter une app", command=lambda: self.ajouter_app(
            {"exe": "", "ecran": "principal", "zone": "plein"})).pack(side="left")
        ttk.Button(boutons, text="▶  Tester les apps", command=self.tester_apps).pack(side="left", padx=12)

    def ajouter_app(self, app):
        ligne = LigneApp(self.cadre_apps, self.prochain_rang, app, self.supprimer_app, self.zones_prises)
        self.prochain_rang += 1
        self.lignes.append(ligne)

    def zones_prises(self, ligne):
        return [l.zone.get() for l in self.lignes if l is not ligne and l.ecran.get() == ligne.ecran.get()]

    def supprimer_app(self, ligne):
        ligne.detruire()
        self.lignes.remove(ligne)

    def page_leds(self, f):
        c = self.cfg["leds"]
        self.led_active = tk.BooleanVar(value=c["active"])
        self.led_motif = tk.StringVar(value=c["motif"])
        self.led_couleur = tk.StringVar(value=c["couleur"])
        self.led_lum = tk.IntVar(value=c["luminosite"])
        self.led_duree = tk.DoubleVar(value=c["duree"])
        self.led_ip = tk.StringVar(value=c["ip"])
        self.ip_affichee = c["ip"]               # pour savoir si l'utilisateur l'a modifiée

        Case(f, "Allumer les LED", self.led_active).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        menu_motif = MenuDeroulant(f, textvariable=self.led_motif, values=cl.MOTIFS, width=18)
        et_motif = self.ligne(f, 1, "Motif de démarrage", menu_motif)
        cadre_c = ttk.Frame(f)
        pastille = tk.Canvas(cadre_c, width=46, height=30, bg=SURFACE, highlightthickness=0, cursor="hand2")

        def dessiner_pastille(*_):
            pastille.delete("all")
            arrondi(pastille, 1, 1, 45, 29, 7, fill=self.led_couleur.get(), outline=BORDURE)

        def choisir_couleur():
            if bouton.instate(["!disabled"]):
                SelecteurCouleur(bouton, self.led_couleur.get(), self.led_couleur.set)

        self.led_couleur.trace_add("write", dessiner_pastille)
        dessiner_pastille()
        pastille.pack(side="left")
        pastille.bind("<Button-1>", lambda e: choisir_couleur())
        bouton = ttk.Button(cadre_c, text="Choisir…", command=choisir_couleur)
        bouton.pack(side="left", padx=12)
        et_couleur = self.ligne(f, 2, "Couleur finale", cadre_c)
        curseur_lum = Curseur(f, self.led_lum, 1, 100, unite="%")
        et_lum = self.ligne(f, 3, "Luminosité", curseur_lum)
        curseur_duree = Curseur(f, self.led_duree, 0, 10, 0.5, unite="s")
        et_duree = self.ligne(f, 4, "Durée du motif", curseur_duree)
        cadre_ip = ttk.Frame(f)
        champ_ip = ttk.Entry(cadre_ip, textvariable=self.led_ip, width=18)
        champ_ip.pack(side="left")
        bouton_ip = ttk.Button(cadre_ip, text="Rechercher", command=self.chercher_leds)
        bouton_ip.pack(side="left", padx=12)
        et_ip = self.ligne(f, 5, "Adresse IP", cadre_ip)

        r = c.get("rythme", {})
        self.rythme_actif = tk.BooleanVar(value=r.get("actif", False))
        self.rythme_mode = tk.StringVar(value=cl.MODES_RYTHME.get(r.get("mode", "mono")))
        self.rythme_sens = tk.IntVar(value=int(r.get("sensibilite", 60)))
        ttk.Separator(f).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        case_rythme = Case(f, "Suivre le rythme de la musique (remplace le motif de démarrage)",
                           self.rythme_actif)
        case_rythme.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 4))
        menu_mode = MenuDeroulant(f, textvariable=self.rythme_mode, width=28,
                                  values=list(cl.MODES_RYTHME.values()))
        et_mode = self.ligne(f, 8, "Couleurs", menu_mode)
        curseur_sens = Curseur(f, self.rythme_sens, 0, 100, 5, unite="%")
        et_sens = self.ligne(f, 9, "Sensibilité", curseur_sens)
        self.rythme_avance = tk.IntVar(value=int(r.get("avance_ms", 150)))
        cadre_a = ttk.Frame(f)
        curseur_avance = Curseur(cadre_a, self.rythme_avance, 0, 500, 10, unite="ms")
        curseur_avance.pack(side="left")
        ttk.Label(cadre_a, style="Discret.TLabel", text="à augmenter si les LED sont en retard").pack(
            side="left", padx=12)
        et_avance = self.ligne(f, 10, "Avance des LED", cadre_a)
        self.rythme_eteindre = tk.BooleanVar(value=r.get("eteindre_silences", True))
        case_eteindre = Case(f, "Éteindre les LED pendant les silences (sinon luminosité minimum)",
                             self.rythme_eteindre)
        case_eteindre.grid(row=11, column=0, columnspan=3, sticky="w", pady=(8, 4))
        self.rythme_actif.trace_add("write", lambda *_: self.prechargement_auto())

        def griser(*_):
            """Grise les réglages sans effet : tout si les LED sont désactivées, le motif en mode
            rythme, les options du rythme sinon."""
            leds, rythme = self.led_active.get(), self.rythme_actif.get()
            groupes = [(leds and not rythme, [et_motif, menu_motif, et_duree, curseur_duree]),
                       (leds, [et_couleur, bouton, et_lum, curseur_lum, et_ip, champ_ip, bouton_ip,
                               case_rythme]),
                       (leds and rythme, [et_mode, menu_mode, et_sens, curseur_sens, et_avance,
                                          curseur_avance, case_eteindre])]
            for actif, widgets in groupes:
                for w in widgets:
                    if hasattr(w, "activer"):
                        w.activer(actif)
                    elif isinstance(w, ttk.Label):
                        w.configure(foreground="" if actif else ETEINT)
                    else:
                        w.state(["!disabled"] if actif else ["disabled"])
            pastille.configure(cursor="hand2" if leds else "")

        self.led_active.trace_add("write", griser)
        self.rythme_actif.trace_add("write", griser)
        griser()
        boutons = ttk.Frame(f)
        boutons.grid(row=12, column=0, columnspan=3, sticky="w", pady=(16, 0))
        ttk.Button(boutons, text="▶  Tester les LED", command=self.tester_leds).pack(side="left")
        ttk.Button(boutons, text="▶  Tester le rythme (avec la musique)",
                   command=self.tester_rythme).pack(side="left", padx=12)

    def page_voix(self, f):
        v = self.cfg["voix"]
        self.voix_active = tk.BooleanVar(value=v["active"])
        self.voix = tk.StringVar(value=v["voix"])
        self.voix_ville = tk.StringVar(value=v["ville"])
        self.voix_secours = tk.StringVar(value=v["secours"])
        self.voix_delai = tk.DoubleVar(value=v["delai"])
        self.coords = (v["ville"], v["lat"], v["lon"])
        self.parties = {nom: (tk.BooleanVar(value=v["parties"][nom]["actif"]),
                              tk.StringVar(value=v["parties"][nom]["texte"])) for nom in cl.PARTIES}

        Case(f, "Runner parle au démarrage", self.voix_active).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        cadre_v = ttk.Frame(f)
        MenuDeroulant(cadre_v, textvariable=self.voix, values=cl.VOIX_DISPO, width=30).pack(side="left")
        BoutonIcone(cadre_v, "lecture", self.ecouter_voix).pack(side="left", padx=(12, 6))
        BoutonIcone(cadre_v, "stop", self.arreter_voix).pack(side="left")
        self.ligne(f, 1, "Voix", cadre_v)
        self.ligne(f, 2, "Ville (météo)", ttk.Entry(f, textvariable=self.voix_ville, width=20))

        ttk.Separator(f).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        ttk.Label(f, text="Phrase principale", style="Titre.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))
        noms = {"accueil": "Accueil", "heure": "Heure", "meteo": "Météo", "cours": "Cours",
                "mails": "Mails", "fin": "Fin"}
        aides = {"heure": "{heure}", "meteo": "{temperature}  {ciel}  {ville}",
                 "cours": "{cours}  {heure_cours}  {salle}", "mails": "{mails}  {nb_mails}"}
        for i, nom in enumerate(cl.PARTIES):
            actif, texte = self.parties[nom]
            Case(f, noms[nom], actif).grid(row=5 + i, column=0, sticky="w", pady=8, padx=(0, 40))
            ttk.Entry(f, textvariable=texte, width=58).grid(row=5 + i, column=1, sticky="w", pady=8)
            if nom in aides:
                ttk.Label(f, text=aides[nom], style="Discret.TLabel").grid(row=5 + i, column=2, sticky="w", padx=14)
            actif.trace_add("write", lambda *_: self.maj_apercu())
            texte.trace_add("write", lambda *_: self.maj_apercu())
        self.apercu_texte = tk.StringVar()
        ttk.Label(f, textvariable=self.apercu_texte, style="Discret.TLabel", wraplength=760,
                  justify="left").grid(row=11, column=1, columnspan=2, sticky="w", pady=(4, 10))
        self.maj_apercu()

        ttk.Separator(f).grid(row=12, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        self.ligne(f, 13, "Phrase de secours", ttk.Entry(f, textvariable=self.voix_secours, width=58))
        self.ligne(f, 14, "Délai après la musique", Curseur(f, self.voix_delai, 0, 10, 0.5, unite="s"))

    def maj_apercu(self):
        """Aperçu de la phrase avec l'heure actuelle (et une météo d'exemple si besoin)."""
        cfg_avant = cl.CFG
        try:
            cl.CFG = dict(cl.CFG, voix=dict(cl.CFG["voix"], ville=self.voix_ville.get(),
                                           parties=self.lire_parties()))
            if hasattr(self, "agenda_actif"):        # page Infos construite : ses réglages actuels
                cl.CFG["infos"] = self.lire_infos()
            meteo = cl._meteo["val"] or (6, 3)
            self.apercu_texte.set("Aperçu : « " + cl.texte_phrase(meteo, apercu=True) + " »")
        except Exception:
            pass
        finally:
            cl.CFG = cfg_avant

    def lire_parties(self):
        return {nom: {"actif": a.get(), "texte": t.get()} for nom, (a, t) in self.parties.items()}

    def page_infos(self, f):
        i = self.cfg["infos"]
        self.agenda_actif = tk.BooleanVar(value=i["agenda"].get("actif", False))
        self.agenda_lien = tk.StringVar(value=i["agenda"].get("lien", ""))
        self.mails_actif = tk.BooleanVar(value=i["mails"].get("actif", False))
        self.ouvrir_webmail = tk.BooleanVar(value=i.get("ouvrir_webmail", True))
        self.recap = tk.BooleanVar(value=i.get("recap", True))

        def titre(rang, texte):
            ttk.Label(f, text=texte, style="Titre.TLabel").grid(row=rang, column=0, sticky="w", pady=(4, 0))

        def aide(rang, texte):
            ttk.Label(f, text=texte, style="Discret.TLabel", wraplength=900, justify="left").grid(
                row=rang, column=0, columnspan=3, sticky="w", pady=(0, 6))

        titre(0, "Emploi du temps")
        Case(f, "Annoncer le prochain cours (partie « Cours » de la phrase, page Voix)", self.agenda_actif).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(f, text="Lien du calendrier (.ics)").grid(row=2, column=0, sticky="w", pady=8, padx=(0, 40))
        ttk.Entry(f, textvariable=self.agenda_lien, width=70).grid(row=2, column=1, columnspan=2, sticky="w", pady=8)
        aide(3, "ADE : bouton « Export agenda » (ou « Exporter »), puis copier le lien proposé (https:// ou webcal://).")

        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        titre(5, "Mails")
        Case(f, "Annoncer les mails non lus (partie « Mails » de la phrase)", self.mails_actif).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=8)
        self.cadre_comptes = ttk.Frame(f)
        self.cadre_comptes.grid(row=7, column=0, columnspan=3, sticky="w")
        for col, txt in enumerate(["Nom", "Adresse", "Serveur IMAP", "Accès", "Webmail"]):
            ttk.Label(self.cadre_comptes, text=txt, style="Titre.TLabel").grid(
                row=0, column=col, padx=(0, 14), sticky="w")
        self.comptes, self.rang_compte = [], 1
        for c in i["mails"].get("comptes", []):
            self.ajouter_compte(c)
        boutons = ttk.Frame(f)
        boutons.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 4))
        for texte, modele in [("+ Gmail", COMPTES_TYPES["Gmail"]), ("+ ENSMA", COMPTES_TYPES["ENSMA"]),
                              ("+ Autre compte", {})]:
            ttk.Button(boutons, text=texte, command=lambda m=modele: self.ajouter_compte(dict(m))).pack(
                side="left", padx=(0, 8))
        aide(9, "Gmail : « Se connecter avec Google », en lecture seule et sans mot de passe dans Runner. "
                "Autres boîtes : serveur IMAP et mot de passe de la messagerie. Mots de passe et connexions sont "
                "gardés par Windows (Gestionnaire d'identification), jamais dans config.json. "
                "Rien n'est marqué comme lu.")

        ttk.Separator(f).grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        Case(f, "Ouvrir le webmail dans le navigateur au lancement", self.ouvrir_webmail).grid(
            row=11, column=0, columnspan=3, sticky="w", pady=6)
        Case(f, "Afficher le récap à l'écran au lancement (cours du jour, derniers mails)", self.recap).grid(
            row=12, column=0, columnspan=3, sticky="w", pady=6)
        tests = ttk.Frame(f)
        tests.grid(row=13, column=0, columnspan=3, sticky="w", pady=(14, 0))
        ttk.Button(tests, text="▶  Tester l'emploi du temps", command=self.tester_agenda).pack(side="left")
        ttk.Button(tests, text="▶  Tester les mails", command=self.tester_mails).pack(side="left", padx=12)
        ttk.Button(tests, text="▶  Voir le récap", command=self.voir_recap).pack(side="left")

    def ajouter_compte(self, compte):
        self.comptes.append(LigneCompte(self.cadre_comptes, self.rang_compte, compte, self.supprimer_compte, self))
        self.rang_compte += 1

    def supprimer_compte(self, ligne):
        ligne.detruire()
        self.comptes.remove(ligne)

    def lire_infos(self):
        return {"agenda": {"actif": self.agenda_actif.get(), "lien": self.agenda_lien.get().strip()},
                "mails": {"actif": self.mails_actif.get(),
                          "comptes": [c.valeur() for c in self.comptes if c.valeur()["adresse"]]},
                "ouvrir_webmail": self.ouvrir_webmail.get(), "recap": self.recap.get()}

    def enregistrer_mots_de_passe(self):
        """Les mots de passe tapés vont dans le Gestionnaire d'identification de Windows."""
        for c in self.comptes:
            mdp, adresse = c.mdp.get(), c.adresse.get().strip()
            if mdp and adresse:
                try:
                    cl.enregistrer_mot_de_passe(adresse, mdp)
                    c.mdp.set("")
                    c.etat_mdp()
                except Exception as e:
                    messagebox.showwarning("Mot de passe", f"Impossible d'enregistrer le mot de passe de {adresse} : {e}")

    def tester_agenda(self):
        self.reglages_actuels()
        if not (cl.CFG["infos"]["agenda"]["actif"] and cl.CFG["infos"]["agenda"]["lien"]):
            self.status.set("Coche « Annoncer le prochain cours » et colle le lien du calendrier")
            return
        self.status.set("Lecture de l'emploi du temps…")

        def tester():
            try:
                os.remove(cl._cache("agenda.ics"))         # téléchargement forcé
            except OSError:
                pass
            tous = cl.agenda()
            if not tous:
                self.dire("Emploi du temps : aucun cours lu (lien correct ? voir le journal)")
                return
            jour = cl.cours_du_jour(tous)
            if jour:
                d, _, titre, lieu = jour[0]
                self.dire(f"Emploi du temps ✓ {len(tous)} cours lus ; prochain aujourd'hui : {titre} à "
                          f"{d:%H:%M}{' (' + lieu + ')' if lieu else ''}")
            else:
                self.dire(f"Emploi du temps ✓ {len(tous)} cours lus ; plus de cours aujourd'hui")
        en_fond(tester)

    def tester_mails(self):
        self.reglages_actuels()
        comptes = [(c.valeur(), c.mdp.get()) for c in self.comptes if c.valeur()["adresse"]]
        if not comptes:
            self.status.set("Ajoute d'abord un compte mail")
            return
        self.status.set("Lecture des mails…")

        def tester():
            res = []
            for compte, mdp in comptes:
                try:
                    b = cl.lire_gmail(compte) if compte.get("type") == "gmail" else cl.lire_boite(compte, mdp or None)
                    res.append(f"{compte['nom'] or compte['adresse']} : {b['non_lus']} non lus ✓")
                except Exception as e:
                    res.append(f"{compte['nom'] or compte['adresse']} : {e}")
            self.dire(" · ".join(res))
        en_fond(tester)

    def voir_recap(self):
        self.enregistrer_mots_de_passe()
        self.reglages_actuels()
        cl._mails["t"] = 0                                  # relecture des mails
        self.status.set("Préparation du récap…")
        en_fond(lambda: (cl.ouvrir_recap(), self.dire("")))

    def page_musique(self, f):
        m = self.cfg["musique"]
        self.musique = tk.StringVar(value=m["fichier"] or AUCUNE)
        self.vol = tk.IntVar(value=m["volume_pct"])
        self.vol_voix = tk.IntVar(value=m["pendant_voix_pct"])
        self.jusqu_a_la_fin = tk.BooleanVar(value=m.get("jusqu_a_la_fin", True))
        self.duree_max = tk.IntVar(value=int(m.get("duree_max_s", 60)))
        self.fondu_fin = tk.DoubleVar(value=m.get("fondu_fin_s", 3.0))

        cadre_m = ttk.Frame(f)
        self.menu_musique = MenuDeroulant(cadre_m, textvariable=self.musique, width=30,
                                          postcommand=self.lister_musiques)
        self.lister_musiques()
        self.menu_musique.bind("<<ComboboxSelected>>", self.choisir_musique)
        self.menu_musique.pack(side="left")
        BoutonIcone(cadre_m, "lecture", self.ecouter_musique).pack(side="left", padx=(12, 6))
        BoutonIcone(cadre_m, "stop", self.arreter_musique).pack(side="left")
        self.puce_rythme = tk.Label(cadre_m, bg=SURFACE, font=(POLICE[0], 11))
        self.puce_rythme.pack(side="left", padx=(16, 0))
        self.musique.trace_add("write", lambda *_: self.prechargement_auto())
        self.ligne(f, 0, "Musique", cadre_m)
        self.ligne(f, 1, "Volume", Curseur(f, self.vol, 0, 100, 5, unite="%"))
        cadre_b = ttk.Frame(f)
        Curseur(cadre_b, self.vol_voix, 0, 100, 5, unite="%").pack(side="left")
        ttk.Label(cadre_b, style="Discret.TLabel", text="100 % = pas de baisse").pack(side="left", padx=12)
        self.ligne(f, 2, "Pendant la voix", cadre_b)
        try:
            sorties = cl.sorties_dispo()
        except Exception:
            sorties = []
        self.sortie = tk.StringVar(value=self.cfg.get("sortie_audio") or SORTIE_AUTO)
        self.ligne(f, 3, "Sortie audio", MenuDeroulant(f, textvariable=self.sortie, width=46,
                                                       values=[SORTIE_AUTO] + sorties))
        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        Case(f, "Jouer la musique jusqu'à la fin", self.jusqu_a_la_fin).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 4))
        curseur_max = Curseur(f, self.duree_max, 10, 600, 10, unite="s")
        et_max = self.ligne(f, 6, "Sinon, arrêter après", curseur_max)
        self.ligne(f, 7, "Fondu de fin", Curseur(f, self.fondu_fin, 0, 10, 0.5, unite="s"))

        def griser_duree(*_):                    # sans effet si la musique est jouée jusqu'au bout
            actif = not self.jusqu_a_la_fin.get()
            curseur_max.activer(actif)
            et_max.configure(foreground="" if actif else ETEINT)

        self.jusqu_a_la_fin.trace_add("write", griser_duree)
        griser_duree()
        ttk.Label(f, style="Discret.TLabel",
                  text="Pour couper la musique : touche Lecture/Pause ou Stop du clavier, ou Ctrl + Alt + M").grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def page_detection(self, f):
        d = self.cfg["detection"]
        try:
            micros = cl.micros_dispo()
        except Exception:
            micros = []
        self.micro = tk.StringVar(value=self.cfg["micro"] or "(par défaut)")
        self.ligne(f, 0, "Micro", MenuDeroulant(f, textvariable=self.micro, width=40,
                                                values=["(par défaut)"] + micros))
        self.det = {}
        reglages = [("brillance_min", "Brillance min", 0.02, 0.5, 0.01),
                    ("attaque_min", "Attaque min", 2, 20, 0.5),
                    ("decroissance_max", "Décroissance max", 0.05, 0.6, 0.01),
                    ("fond_min", "Au-dessus du bruit de fond", 2, 20, 0.5),
                    ("seuil_min", "Volume minimum", 0.005, 0.1, 0.005),
                    ("ecart_max", "Écart max entre 2 claps", 0.4, 1.5, 0.05)]
        for i, (cle, txt, mini, maxi, pas) in enumerate(reglages, start=1):
            self.det[cle] = tk.DoubleVar(value=d[cle])
            self.ligne(f, i, txt, Curseur(f, self.det[cle], mini, maxi, pas,
                                          unite={"ecart_max": "s", "fond_min": "fois"}.get(cle, "")))
        boutons = ttk.Frame(f)
        boutons.grid(row=8, column=0, columnspan=3, sticky="w", pady=(16, 0))
        ttk.Button(boutons, text="▶  Calibrer automatiquement", style="Accent.TButton",
                   command=lambda: Calibrage(self)).pack(side="left")
        ttk.Button(boutons, text="Valeurs par défaut", command=self.detection_par_defaut).pack(side="left", padx=12)
        ttk.Button(boutons, text="▶  Mode réglage (affiche l'analyse des sons)",
                   command=self.mode_debug).pack(side="left")

    def detection_par_defaut(self):
        for cle, var in self.det.items():
            var.set(cl.DEFAUT["detection"][cle])
        self.status.set("Détection : valeurs par défaut (pense à enregistrer)")

    def page_systeme(self, f):
        sy = self.cfg["systeme"]
        self.demarrage = tk.BooleanVar(value=os.path.exists(cl.RACCOURCI_DEMARRAGE))
        self.reveil_initial = sy.get("reveil", False)
        self.reveil = tk.BooleanVar(value=self.reveil_initial)

        def verifier_reveil():                   # schtasks prend un instant : sans bloquer l'ouverture
            try:
                cl.migrer_tache_reveil()
                actif = cl.reveil_actif()
            except Exception:
                return
            def appliquer():
                self.reveil_initial = actif
                self.reveil.set(actif)
            self.after(0, appliquer)
        en_fond(verifier_reveil)
        self.point_acces = tk.BooleanVar(value=sy["point_acces"])
        self.attente_max = tk.DoubleVar(value=sy.get("attente_max", 3.0))
        self.ecoute_max = tk.IntVar(value=int(sy.get("ecoute_max_min", 10)))
        self.raccourci = tk.StringVar(value=cl.RACCOURCIS.get(sy.get("raccourci", ""), sy.get("raccourci", "")))
        Case(f, "Lancer Runner à l'ouverture de session Windows", self.demarrage).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=6)
        Case(f, "Lancer Runner à la sortie de veille", self.reveil).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=6)
        Case(f, "Activer le point d'accès Wi-Fi du PC au lancement de Runner", self.point_acces).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(f, text="▶  Activer le point d'accès maintenant", command=self.activer_wifi).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=18)
        self.ligne(f, 5, "Attente max avant lancement", Curseur(f, self.attente_max, 1, 15, 0.5, unite="s"))
        cadre_e = ttk.Frame(f)
        Curseur(cadre_e, self.ecoute_max, 0, 60, 1, unite="min").pack(side="left")
        ttk.Label(cadre_e, style="Discret.TLabel", text="0 = jamais").pack(side="left", padx=12)
        self.ligne(f, 6, "Arrêt de l'écoute sans clap", cadre_e)
        cadre_r = ttk.Frame(f)
        MenuDeroulant(cadre_r, textvariable=self.raccourci, values=list(cl.RACCOURCIS.values()),
                      width=20).pack(side="left")
        ttk.Label(cadre_r, style="Discret.TLabel",
                  text="déclenche Runner comme un double clap ; reste actif après l'arrêt du micro").pack(
            side="left", padx=12)
        self.ligne(f, 7, "Raccourci clavier", cadre_r)

    def page_journal(self, f):
        barre = ttk.Frame(f)
        barre.pack(fill="x", pady=(0, 12))
        self.alertes_seulement = tk.BooleanVar(value=False)
        Case(barre, "Alertes et erreurs seulement", self.alertes_seulement).pack(side="left")
        ttk.Button(barre, text="Ouvrir le fichier", command=self.ouvrir_journal).pack(side="right")
        ttk.Button(barre, text="Effacer", command=self.effacer_journal).pack(side="right", padx=8)
        cadre = tk.Frame(f, bg=FONCE)
        cadre.pack(fill="both", expand=True)
        self.texte_journal = tk.Text(cadre, bg=CHAMP, fg=TEXTE, font=("Consolas", 11), relief="flat",
                                     bd=0, wrap="none", padx=14, pady=10, highlightthickness=0,
                                     insertbackground=TEXTE, state="disabled")
        defile = ttk.Scrollbar(cadre, orient="vertical", command=self.texte_journal.yview)
        self.texte_journal.configure(yscrollcommand=defile.set)
        defile.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.texte_journal.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        self.texte_journal.tag_configure("date", foreground=DISCRET)
        self.texte_journal.tag_configure("WARNING", foreground="#e0b35a")
        self.texte_journal.tag_configure("ERROR", foreground="#e8735f")
        self.alertes_seulement.trace_add("write", lambda *_: self.charger_journal(force=True))
        self.page_actuelle, self._journal_modif = "Apps", None
        self.after(1500, self.surveiller_journal)

    def surveiller_journal(self):
        if self.page_actuelle == "Journal":
            self.charger_journal()
        self.maj_puce()
        # Lancement par clap en arrière-plan (démarrage, sortie de veille) : on propose « Stop »
        en_cours = cl.lancement_en_cours() and not (self.processus_test and self.processus_test.poll() is None)
        if en_cours and "fond" not in self.tests:
            self.tests.add("fond")
            self.status.set("Musique lancée par Runner en cours")
            self.bouton_stop.pack(side="right", padx=(0, 8))
        elif not en_cours and "fond" in self.tests:
            self.fin_test("fond", "")
        self.after(1500, self.surveiller_journal)

    def charger_journal(self, force=False):
        """Affiche les 800 dernières lignes de runner.log (relu seulement s'il a changé)."""
        try:
            modif = os.path.getmtime(cl.FICHIER_LOG)
            with open(cl.FICHIER_LOG, encoding="utf-8", errors="replace") as fichier:
                fichier.seek(max(0, os.path.getsize(cl.FICHIER_LOG) - 300_000))
                lignes = fichier.read().splitlines()[-800:]
        except OSError:
            modif, lignes = None, ["(journal vide)"]
        if modif == self._journal_modif and not force:
            return
        self._journal_modif = modif
        t = self.texte_journal
        en_bas = t.yview()[1] > 0.98
        t.configure(state="normal")
        t.delete("1.0", "end")
        niveau = "INFO"
        for ligne in lignes:
            m = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(\w+)\s+(.*)$", ligne)
            if m:
                niveau = m.group(2)
            if self.alertes_seulement.get() and niveau == "INFO":
                continue
            if m:
                t.insert("end", m.group(1) + "  ", "date")
                t.insert("end", m.group(3) + "\n", niveau if niveau != "INFO" else ())
            else:                                       # suite d'une erreur (détail technique)
                t.insert("end", ligne + "\n", niveau if niveau != "INFO" else ())
        t.configure(state="disabled")
        if en_bas or force:
            t.see("end")

    def effacer_journal(self):
        try:
            open(cl.FICHIER_LOG, "w").close()
            self.status.set("Journal effacé")
        except OSError as e:
            self.status.set(f"Impossible d'effacer le journal : {e}")
        self.charger_journal(force=True)

    def ouvrir_journal(self):
        if os.path.exists(cl.FICHIER_LOG):
            os.startfile(cl.FICHIER_LOG)

    # --------------------------- Lecture / écriture ---------------------------
    def lire(self):
        _, lat, lon = self.coords
        musique = self.musique.get()
        return {
            "micro": "" if self.micro.get() == "(par défaut)" else self.micro.get(),
            "detection": {k: round(v.get(), 3) for k, v in self.det.items()},
            "leds": {"active": self.led_active.get(), "ip": self.ip_a_enregistrer(),
                     "motif": self.led_motif.get(), "couleur": self.led_couleur.get(),
                     "luminosite": self.led_lum.get(), "duree": nombre(self.led_duree, 3.0),
                     "rythme": {"actif": self.rythme_actif.get(),
                                "mode": next((k for k, v in cl.MODES_RYTHME.items()
                                              if v == self.rythme_mode.get()), "mono"),
                                "sensibilite": self.rythme_sens.get(),
                                "avance_ms": self.rythme_avance.get(),
                                "eteindre_silences": self.rythme_eteindre.get()}},
            "voix": {"active": self.voix_active.get(), "voix": self.voix.get().strip(),
                     "ville": self.voix_ville.get().strip(), "lat": lat, "lon": lon,
                     "delai": nombre(self.voix_delai, 1.0), "parties": self.lire_parties(),
                     "secours": self.voix_secours.get().strip()},
            "musique": {"fichier": "" if musique == AUCUNE else musique,
                        "volume_pct": self.vol.get(), "pendant_voix_pct": self.vol_voix.get(),
                        "jusqu_a_la_fin": self.jusqu_a_la_fin.get(),
                        "duree_max_s": int(nombre(self.duree_max, 60)),
                        "fondu_fin_s": nombre(self.fondu_fin, 3.0)},
            "apps": [v for v in (l.valeur() for l in self.lignes) if v["exe"]],
            "sortie_audio": "" if self.sortie.get() == SORTIE_AUTO else self.sortie.get(),
            "systeme": {"point_acces": self.point_acces.get(),
                        "demarrage_session": self.demarrage.get(),
                        "reveil": self.reveil.get(),
                        "attente_max": nombre(self.attente_max, 3.0),
                        "ecoute_max_min": int(nombre(self.ecoute_max, 10)),
                        "raccourci": next((k for k, v in cl.RACCOURCIS.items() if v == self.raccourci.get()),
                                          self.raccourci.get())},
            "infos": self.lire_infos(),
        }

    def ip_a_enregistrer(self):
        """Adresse tapée ou trouvée dans la fenêtre ; sinon celle que Runner a pu mémoriser
        entre-temps dans config.json (elle n'est donc jamais écrasée par une ancienne)."""
        ip = self.led_ip.get().strip()
        if ip and ip != self.ip_affichee:
            return ip
        try:
            with open(cl.FICHIER_CONFIG_REEL, encoding="utf-8") as f:
                ip_fichier = json.load(f).get("leds", {}).get("ip", "")
        except (OSError, ValueError, AttributeError):
            ip_fichier = ""
        return ip_fichier or ip

    def maj_ville(self):
        ville = self.voix_ville.get().strip()
        if ville != self.coords[0]:
            pos = cl.geocoder(ville)
            if pos:
                self.coords = (ville, *pos)
            else:
                messagebox.showwarning("Ville introuvable",
                                       f"Impossible de trouver « {ville} ». L'ancienne position est gardée.")

    def reglages_actuels(self):
        """Réglages de la fenêtre (enregistrés ou non), appliqués aux tests."""
        self.maj_ville()
        cl.CFG = self.lire()
        return cl.CFG

    def enregistrer(self):
        cfg = self.reglages_actuels()
        try:
            cl.sauver_config(cfg)
        except OSError as e:
            messagebox.showerror("Enregistrement", f"Impossible d'enregistrer les réglages : {e}")
            return cfg
        try:
            cl.regler_demarrage_session(cfg["systeme"]["demarrage_session"])
        except Exception as e:
            messagebox.showwarning("Démarrage", f"Impossible de régler le lancement au démarrage : {e}")
        if cfg["systeme"]["reveil"] != self.reveil_initial:
            try:
                cl.regler_reveil(cfg["systeme"]["reveil"])
                self.reveil_initial = cfg["systeme"]["reveil"]
            except Exception as e:
                messagebox.showwarning("Sortie de veille",
                                       f"Impossible de régler le lancement à la sortie de veille : {e}")
        self.enregistrer_mots_de_passe()
        self.ip_affichee = cfg["leds"]["ip"]
        self.led_ip.set(cfg["leds"]["ip"])
        self.status.set("Réglages enregistrés ✓")
        return cfg

    # -------------------------------- Tests --------------------------------
    def debut_test(self, nom, message):
        cl.print(f"Test « {nom} » : {message}")
        self.tests.add(nom)
        cl.ARRET.clear()
        cl.ARRET_LEDS.clear()
        self.status.set(message)
        self.bouton_stop.pack(side="right", padx=(0, 8))

    def fin_test(self, nom, message=None):
        if message:
            cl.print(f"Test « {nom} » : {message}")

        def fin():
            self.tests.discard(nom)
            if message is not None:
                self.status.set(message)
            if not self.tests:
                self.bouton_stop.pack_forget()
        self.after(0, fin)

    def tester_tout(self):
        """Comme à l'allumage du PC : point d'accès, écoute du clap, puis tout le lancement.
        Utilise les réglages de la fenêtre, même non enregistrés."""
        if self.processus_test and self.processus_test.poll() is None:
            self.status.set("Un test est déjà en cours")
            return
        fichier = os.path.join(tempfile.gettempdir(), "runner_test_config.json")
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(self.reglages_actuels(), f, ensure_ascii=False)
        self.processus_test = subprocess.Popen(
            [PYTHON, os.path.join(cl.DOSSIER, "clap_launcher.py"), "--config", fichier],
            cwd=cl.DOSSIER, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.debut_test("clap", "En écoute : tape deux fois dans tes mains…")
        self.surveiller_test()

    def surveiller_test(self):
        p = self.processus_test
        if p and p.poll() is None:
            self.after(500, self.surveiller_test)
        elif "clap" in self.tests:
            self.fin_test("clap", "Test terminé")

    def tester_apps(self):
        self.reglages_actuels()
        self.debut_test("apps", "Lancement des apps…")
        en_fond(lambda: (cl.lancer_et_placer_apps(), self.fin_test("apps", "Apps lancées et placées ✓")))

    def tester_leds(self):
        self.reglages_actuels()
        self.debut_test("leds", "Test des LED…")
        motif = "fixe" if self.rythme_actif.get() else None
        en_fond(lambda: (cl.animer_leds(motif=motif), self.fin_test("leds", "Test des LED terminé")))

    def musique_choisie(self):
        m = self.musique.get() if hasattr(self, "musique") else AUCUNE
        return cl.chemin_musique(m) if m not in (AUCUNE, PARCOURIR) else None

    def maj_puce(self):
        """Pastille à côté de la musique : rythme préchargé, en cours ou à faire."""
        if not hasattr(self, "puce_rythme"):
            return
        f = self.musique_choisie()
        if not (self.rythme_actif.get() and f):
            self.puce_rythme.configure(text="")
            return
        etat = "en_cours" if getattr(self, "_prechargement", None) == f else cl.etat_prechargement(f)
        texte, couleur = {"pret": ("●  Rythme préchargé", "#8fbf7a"),
                          "en_cours": ("◌  Préchargement…", ACCENT),
                          "absent": ("○  Pas encore préchargé", DISCRET)}[etat]
        self.puce_rythme.configure(text=texte, fg=couleur)

    def prechargement_auto(self):
        """Précharge le rythme de la musique choisie dès que c'est nécessaire (mode rythme actif)."""
        f = self.musique_choisie()
        if f and self.rythme_actif.get() and cl.etat_prechargement(f) == "absent" \
                and getattr(self, "_prechargement", None) != f:
            self._prechargement = f

            def precharger():
                cl.precharger_rythme(f)
                self._prechargement = None
                self.after(0, self.maj_puce)
            en_fond(precharger)
        self.maj_puce()

    def tester_rythme(self):
        """Précharge si besoin, joue la musique choisie et fait suivre son rythme aux LED."""
        self.arreter_apercu()
        self.reglages_actuels()
        f = self.musique_choisie()
        if not f:
            self.status.set("Choisis d'abord une musique (page Musique)")
            return
        self.debut_test("rythme", "Test du rythme…")
        volume = self.vol.get() / 100

        def suivre():
            if cl.etat_prechargement(f) != "pret":
                self.dire("Préchargement du rythme…")
                self._prechargement = f
                self.after(0, self.maj_puce)
                ok = cl.precharger_rythme(f)
                self._prechargement = None
                self.after(0, self.maj_puce)
                if not ok:
                    self.fin_test("rythme", "Préchargement impossible (voir le journal)")
                    return
            ips, _ = cl.trouver_leds()
            if not ips:
                self.fin_test("rythme", "Aucune LED trouvée")
                return
            if cl.ARRET.is_set():
                self.fin_test("rythme", "")
                return
            try:
                self.apercu = lecteur = cl.Lecteur(f, volume).jouer()
            except Exception as e:
                self.fin_test("rythme", f"Lecture impossible : {e}")
                return
            self.dire("Les LED suivent la musique…")
            cl.rythme_leds(lecteur, ips, f)
            self.fin_test("rythme", "Test du rythme terminé")
        en_fond(suivre)

    def chercher_leds(self):
        self.status.set("Recherche des LED…")

        def chercher():
            trouvees = cl.chercher_leds(2.0)
            if trouvees:
                ip, sku = next(iter(trouvees.items()))
                self.after(0, self.led_ip.set, ip)
                self.dire(f"LED trouvée : {sku} à {ip}")
            else:
                self.dire("Aucune LED trouvée")
        en_fond(chercher)

    def ecouter_voix(self):
        self.reglages_actuels()
        self.debut_test("voix", "Synthèse de la voix…")

        def ecouter():
            try:
                f = os.path.join(tempfile.gettempdir(), "runner_apercu.wav")
                cl.synthetiser(cl.texte_phrase(), cl.CFG["voix"]["voix"], f)
                if not cl.ARRET.is_set():
                    self.dire("Lecture…")
                    self.lecteur_voix = cl.Lecteur(f).jouer()
                    self.lecteur_voix.attendre(cl.ARRET.is_set)
                self.fin_test("voix", "")
            except Exception as e:
                self.fin_test("voix", f"Voix indisponible : {e}")
        en_fond(ecouter)

    def lister_musiques(self):
        self.menu_musique["values"] = [AUCUNE] + cl.musiques_dispo() + [PARCOURIR]

    def choisir_musique(self, _):
        if self.musique.get() == PARCOURIR:
            f = filedialog.askopenfilename(title="Choisir une musique", initialdir=cl.DOSSIER,
                                           filetypes=[("Audio", " ".join("*" + e for e in cl.EXTENSIONS_AUDIO))])
            self.musique.set(os.path.normpath(f) if f else AUCUNE)

    def ecouter_musique(self):
        self.arreter_apercu()
        self.reglages_actuels()
        f = cl.chemin_musique(self.musique.get()) if self.musique.get() != AUCUNE else None
        if not f:
            return
        try:
            self.apercu = cl.Lecteur(f, self.vol.get() / 100).jouer()
        except Exception as e:
            self.status.set(f"Lecture impossible : {e}")
            return
        self.debut_test("musique", "Lecture de la musique…")
        lecteur = self.apercu
        en_fond(lambda: (lecteur.fini.wait(), self.fin_test("musique", "")))

    def arreter_apercu(self):
        if self.apercu:
            self.apercu.arreter()
            self.apercu = None

    def arreter_musique(self):
        self.arreter_apercu()
        self.fin_test("musique", "")

    def arreter_voix(self):
        if self.lecteur_voix:
            self.lecteur_voix.arreter()
        self.fin_test("voix", "")

    def arreter(self):
        """Stop général : coupe tous les tests en cours. Les LED ne sont éteintes que si un test
        les utilisait (test des LED ou test complet)."""
        leds_concernees = bool(self.tests & {"leds", "clap", "rythme"})
        cl.ARRET.set()
        if leds_concernees:
            cl.ARRET_LEDS.set()
        self.arreter_apercu()
        if self.lecteur_voix:
            self.lecteur_voix.arreter()
        p = self.processus_test
        if p and p.poll() is None:
            cl.demander_arret(leds=leds_concernees)
            self.after(2500, lambda: p.poll() is None and p.terminate())
        elif "fond" in self.tests:                     # musique lancée par Runner en arrière-plan
            cl.demander_arret(leds=False)
        if leds_concernees:
            en_fond(cl.eteindre_leds)
        self.status.set("Arrêté")

        def nettoyer():
            if os.path.exists(cl.FICHIER_STOP):
                os.remove(cl.FICHIER_STOP)
            self.tests.clear()
            self.bouton_stop.pack_forget()
        self.after(3000, nettoyer)

    def activer_wifi(self):
        self.status.set("Activation du point d'accès…")

        def activer():
            ok, msg = cl.activer_point_acces()
            textes = {"ACTIVE": "Point d'accès activé ✓", "DEJA_ACTIF": "Point d'accès déjà actif ✓",
                      "PAS_INTERNET": "Pas de connexion Internet à partager"}
            self.dire(textes.get(msg, f"Échec : {msg}"))
        en_fond(activer)

    def mode_debug(self):
        fichier = os.path.join(tempfile.gettempdir(), "runner_test_config.json")
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(self.reglages_actuels(), f, ensure_ascii=False)
        subprocess.Popen([PYTHON, os.path.join(cl.DOSSIER, "clap_launcher.py"), "--debug",
                          "--config", fichier], cwd=cl.DOSSIER, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def fermer(self):
        if self.tests:
            self.arreter()
        self.destroy()


if __name__ == "__main__":
    cl.masquer_messages_bibliotheques()
    if "--recap" in sys.argv:                     # fenêtre de récap ouverte par Runner au lancement
        cl.configurer_journal("récap")
        Recap(sys.argv[sys.argv.index("--recap") + 1]).mainloop()
    else:
        cl.configurer_journal("réglages")
        Fenetre().mainloop()
