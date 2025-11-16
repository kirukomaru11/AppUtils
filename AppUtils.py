import os
from math import sqrt
from marshal import loads as marshal
from marshal import dumps as marshal_string
from operator import itemgetter
from concurrent.futures import ThreadPoolExecutor
from xml.etree.ElementTree import fromstring as xml
from xml.etree.ElementTree import tostring as xml_string
from zipfile import ZipFile

import gi
gi.require_version("Adw", "1")
gi.require_version("Soup", "3.0")
from gi.repository import Adw, Gtk, GLib, Gio, Gdk, GdkPixbuf, GObject, Pango, Soup

try:
    gi.require_version("GlyGtk4", "2")
    from gi.repository import GlyGtk4
    from gi.repository import Gly
    GLY = True
except:
    GLY = False
    print("Glycin not available")

css = Gtk.CssProvider.new()
css.load_from_string("""
masonrybox view { border-spacing: 10px; margin: 10px; }
masonrybox view > column { border-spacing: 10px; }
.entry-dialog entry text { margin: 12px 5px 12px 5px; }
.entry-dialog textview { background: color-mix(in srgb, currentColor 8%, transparent); border-radius: 10px; padding: 12px; font-size: 16px; }
.entry-dialog .message-area  { border-spacing: 16px; }
media, masonrybox picture, media picture { border-radius: 13px; }
media controls.toolbar.card { background: rgba(0, 0, 0, 0.3); color: white; margin: 6px; }
controls.toolbar.card box > scale { padding: 0px; }
.tagrow wrap-box { padding: 4px; }
.tagrow box { padding: 12px;  border-spacing: 6px; }
.tagrow tag { background: color-mix(in srgb, currentColor 10%, transparent); color: inherit; border-radius: 99px; padding-left:10px; }
.tagrow tag button { margin: 3px; min-width: 0; min-height: 0; padding: 6px; }
.tagrow pinnedtag { background: color-mix(in srgb, currentColor 10%, transparent); color: inherit; border-radius: 99px; padding: 6px 12px 6px 12px; }
row.destructive-action { background: var(--destructive-bg-color); color: white; }
""")
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)

class TagRow(Adw.PreferencesRow):
    __gtype_name__ = "TagRow"
    
    @GObject.Property(type=GObject.Strv, flags=GObject.ParamFlags.READWRITE)
    def pinned_tags(self): return self._pinned_tags
    @pinned_tags.setter
    def pinned_tags(self, value):
        self._pinned_tags = value
        GLib.idle_add(self.sync_tags)
    
    @GObject.Property(type=GObject.Strv, flags=GObject.ParamFlags.READWRITE)
    def tags(self): return self._tags
    @tags.setter
    def tags(self, value):
        self._tags = value
        GLib.idle_add(self.sync_tags)
            
    @GObject.Signal(flags=GObject.SignalFlags.RUN_LAST, return_type=bool, arg_types=(Gtk.Widget,), accumulator=GObject.signal_accumulator_true_handled)
    def tag_widget_added(self, *args): return
    
    def __init__(self, tags=[], **kwargs):
        self._tags, self._pinned_tags = tags, []
        self.prompt = EntryDialog(lambda d: (d.tagrow.set_property("tags", d.tagrow.tags + [d.get_extra_child().get_text()]), d.close(), d.tagrow.grab_focus()), heading="New Tag")
        self.prompt.tagrow = self
        self.button, self.wrapbox = Gtk.Box(halign=Gtk.Align.CENTER), Adw.WrapBox(tooltip_text="Add Tag", child_spacing=4, line_spacing=4)
        self.button.append(Gtk.Image(icon_name="list-add-symbolic"))
        self.button.append(Gtk.Label(css_classes=("heading",), label="Add Tag"))
        super().__init__(**kwargs)
        click = Gtk.GestureClick()
        click.connect("released", tagrow_clicked)
        self.add_controller(click)
        self.connect("activate", lambda r: (self.prompt.present(r.get_root()), self.prompt.get_extra_child().grab_focus())[0])
        self.add_css_class("tagrow")
        self.sync_tags()
        
    def sync_tags(self) -> None:
        self.wrapbox.remove_all()
        self.set_child(self.wrapbox if (self._pinned_tags or self._tags) else self.button)
        for i in self._pinned_tags:
            w = Gtk.Button(can_shrink=True, halign=Gtk.Align.START, css_classes=("pill",), css_name="pinnedtag", label=i)
            self.wrapbox.append(w)
            self.emit("tag-widget-added", w)
        for i in self._tags:
            w = Gtk.Box(css_classes=("pill",), halign=Gtk.Align.START, css_name="tag")
            r = Gtk.Button(icon_name="window-close-symbolic", css_classes=("flat", "circular"), tooltip_text="Remove Tag")
            r.connect("clicked", lambda b: (t := b.get_ancestor(TagRow), t.set_property("tags", tuple(i for i in t.tags if not i == b.get_prev_sibling().get_label())), t.grab_focus())[1])
            for it in (Gtk.Label(use_markup=True, tooltip_text=i if len(i) > 20 else "", label=i, ellipsize=Pango.EllipsizeMode.END), r): w.append(it)
            self.wrapbox.append(w)
            self.emit("tag-widget-added", w)
def tagrow_clicked(e: Gtk.GestureClick, n: int, x: float, y: float) -> None:
    w = e.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
    if not w.get_ancestor(Adw.WrapBox) or isinstance(w, Adw.WrapBox): e.get_widget().prompt.present(e.get_widget().get_root())

def App(args=None, style=None, shortcuts={}, metainfo="", activate=lambda a: (a.window.set_application(a) if not a.get_active_window() else None, a.window.present()), shutdown=lambda a: (data_save(), app.thread.shutdown(wait=True, cancel_futures=True)), file_open=None, data={}, **kwargs) -> Adw.Application:
    global app
    app = Adw.Application(**kwargs)
    app.register()
    if app.get_is_remote():
        app.run(args) if args else app.run()
        exit()
    Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(os.path.join(GLib.get_system_data_dirs()[0], app.get_application_id()))
    if style:
        css = Gtk.CssProvider.new()
        css.load_from_string(style)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    app.about = About(metainfo if metainfo else GLib.build_filenamev((GLib.get_system_data_dirs()[0], "metainfo", f"{app.get_application_id()}.metainfo.xml")))
    app.session = Soup.Session(user_agent=app.about.get_application_name(), max_conns_per_host=10)
    app.name = app.about.get_application_name()
    app.shortcuts = Shortcuts(shortcuts)
    Action("about", lambda *_: app.about.present(app.get_active_window()))
    Action("shortcuts", lambda *_: app.shortcuts.present(app.get_active_window()), "<primary>question")
    app.default_menu = Menu((("Keyboard Shortcuts", "shortcuts"), (f"About {app.about.get_application_name()}", "about"), ),)
    app.window = Adw.ApplicationWindow(content=Adw.ToastOverlay(), title=app.about.get_application_name())
    app.spinner = Adw.SpinnerPaintable.new(app.window.get_content())
    if data != {}:
        app.data_folder = Gio.File.new_for_path(os.path.join(GLib.get_user_data_dir(), app.about.get_application_name().lower()))
        if not os.path.exists(app.data_folder.peek_path()): app.data_folder.make_directory_with_parents()
        app.data_file = app.data_folder.get_child(app.about.get_application_name())
        app.data = marshal(app.data_file.load_contents()[1]) if os.path.exists(app.data_file.peek_path()) else data
        data_default(app.data, data)
        if "Window" in app.data:
            for i in app.data["Window"]: Action(i, stateful=app.data["Window"][i]).bind_property("state", app.window, i, GObject.BindingFlags.DEFAULT | GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE, lambda b, v: v.unpack(), lambda b, v: GLib.Variant(b.get_source().get_property("state-type").dup_string(), v))
    if activate: app.connect("activate", activate)
    if shutdown: app.connect("shutdown", shutdown)
    if file_open: app.connect("open", file_open)
    app.uri_launcher = Gtk.UriLauncher.new()
    app.file_launcher = Gtk.FileLauncher.new()
    app.persist = []
    app.thread = ThreadPoolExecutor()
    return app

def Action(name: str, callback=None, accels="", stateful=None) -> Gio.Action:
    if stateful == None:
        action = Gio.SimpleAction.new(name, None)
    else:
        _type = "s" if type(stateful) == str else "i" if type(stateful) == int else "b"
        action = Gio.SimpleAction.new_stateful(name, GLib.VariantType(_type) if _type == "s" else None, GLib.Variant(_type, stateful))
    app.add_action(action)
    if accels != "":
        app.set_accels_for_action(f"app.{name}", accels.split(" "))
    if callback:
        if stateful == None: action.connect("activate", callback)
        else: action.connect("notify::state", callback)
    return action

def About(metainfo: str) -> Adw.AboutDialog:
    content = xml(Gio.File.new_for_path(metainfo).load_contents()[1].decode("utf-8"))
    return Adw.AboutDialog(application_name=content.findtext("./name"), issue_url=content.findtext("./url[@type='bugtracker']"), website=content.findtext("./url[@type='homepage']"), application_icon=content.findtext("./id") + "-symbolic", license_type=getattr(Gtk.License, tuple(it for it in dir(Gtk.License) if it.startswith(content.findtext("./project_license")))[0]), developer_name=content.findtext("./developer/name"), version=content.find("./releases/release").attrib["version"], release_notes=(xml_string(content.find("./releases/release/description"), encoding="unicode").replace("</description>", "").replace("<description>", "")))

def Shortcuts(shortcuts: dict) -> Adw.ShortcutsDialog:
    _shortcuts = Adw.ShortcutsDialog()
    for section in shortcuts:
        _section = Adw.ShortcutsSection(title=section)
        for title, a in shortcuts[section]: _section.add(Adw.ShortcutsItem(title=title, action_name=a if "app." in a else "", accelerator=a if not "app." in a else ""))
        _shortcuts.add(_section)
    return _shortcuts
    
def Button(t=Gtk.Button, callback=None, icon_name="", bindings=(), **kargs) -> Gtk.Button | Gtk.MenuButton | Gtk.ToggleButton:
    button = t(icon_name=icon_name + "-symbolic" if icon_name else "", **kargs)
    if callback: button.connect("clicked" if type(button) == Gtk.Button else "notify::active", callback)
    for b in bindings:
        source = b[0] if b[0] else button
        source.bind_property(b[1], b[2] if b[2] else button, b[3], b[4] if len(b) >= 5 and b[4] else GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE, b[5] if len(b) >= 6 else None)
    return button

def Menu(*args, freeze=True) -> Gio.Menu:
    menu = Gio.Menu.new()
    for i in args:
        _menu = i if isinstance(i, Gio.Menu) else menu if len(args) == 1 else Gio.Menu.new()
        if not isinstance(i, Gio.Menu):
            if isinstance(i[0], str):
                __menu = _menu if len(args) == 1 else Gio.Menu.new()
                for it in i[1][1]: __menu.append(it, f"app.{i[1][0]}::{it}")
                if _menu != __menu: _menu.append_submenu(i[0], __menu)
            else:
                for t, a in i: _menu.append(t, "app." + a)
        if menu != _menu:
            menu.append_section(None, _menu)
            if freeze: _menu.freeze()
    menu.freeze()
    return menu

def Toast(title: str, message=None, **kwargs) -> None:
    if message: print(message)
    else: print(title)
    toast_overlay = app.window.get_visible_dialog() if isinstance(app.window.get_visible_dialog(), Adw.PreferencesDialog) else app.window.get_content()
    GLib.idle_add(toast_overlay.add_toast, Adw.Toast(title=title, use_markup=False, **kwargs))
    return

default_finish = lambda p, pp: None
def Media(uri: Gio.File | None | str, child=None, scrollable=None, parent_type=Gtk.Picture, mimetype="", play=True, finish_func=default_finish, media=False, **kwargs) -> Gtk.Widget:
    if isinstance(uri, str):
        uri = Gio.File.new_for_uri(uri)
    if uri and not mimetype:
        mimetype = Gio.content_type_guess(uri.get_uri())[0]
    pargs = dict(((i[0].replace("p__", ""), i[1]) for i in kwargs.items() if i[0].startswith("p__")))
    cargs = dict(((i[0].replace("c__", ""), i[1]) for i in kwargs.items() if i[0].startswith("c__")))
    if not pargs and parent_type is Gtk.Overlay:
        pargs = {"css_name": "media", "overflow": Gtk.Overflow.HIDDEN}
    parent = parent_type(**pargs)
    if mimetype.startswith("audio"):
        controls = Gtk.MediaControls(hexpand=True, media_stream=Gtk.MediaFile.new_for_file(uri), css_classes=("toolbar", "card"))
        for i in ("time_label", "duration_label"): GLib.idle_add(controls.get_template_child(Gtk.MediaControls, i).unparent)
        return controls
    picture = parent if (parent_type is Adw.Avatar or parent_type is Gtk.Picture) else child if child else Gtk.Picture(**cargs)
    if parent_type is Gtk.Picture or parent_type is Adw.Avatar:
        parent = picture
    elif not scrollable == None and parent_type is Gtk.Overlay:
        scrolled = Gtk.ScrolledWindow(child=Gtk.Viewport(child=picture, vscroll_policy=scrollable), propagate_natural_height=True, propagate_natural_width=True)
        scrolled.get_child().bind_property("vscroll-policy", scrolled.get_child(), "hscroll-policy", GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE)
        parent.set_child(scrolled)
    else: parent.set_child(picture)
    if parent_type is Gtk.Overlay:
        parent.event = Gtk.EventControllerMotion()
        parent.add_controller(parent.event)
    if uri and mimetype or isinstance(picture, Gtk.Picture) and not "paintable" in pargs:
        GLib.idle_add(picture.set_paintable if hasattr(picture, "set_paintable") else picture.set_custom_image, app.spinner)
        GLib.idle_add(picture.add_css_class, "spinner")
    if mimetype.startswith("video"):
        picture.media = Gtk.MediaFile.new_for_file(uri)
        picture.sig = picture.media.connect("invalidate-contents", media_finish, (picture, finish_func))
        if parent_type is Gtk.Overlay:
            parent.controls = Gtk.MediaControls(hexpand=True, valign=Gtk.Align.END, css_classes=("toolbar", "card"), vexpand=True, media_stream=picture.media)
            for i in ("time_label", "duration_label"): GLib.idle_add(parent.controls.get_template_child(Gtk.MediaControls, i).unparent)
            revealer = Gtk.Revealer(child=parent.controls, transition_type=Gtk.RevealerTransitionType.CROSSFADE, valign=Gtk.Align.END)
            parent.event.bind_property("contains-pointer", revealer, "reveal-child", GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE, toggle_revealer)
            revealer.controls = parent.controls
            parent.add_overlay(revealer)
        if play == True: picture.media.set_properties(playing=True, loop=True)
    elif mimetype.startswith("image") or mimetype.endswith("zip"): app.thread.submit(load_image, picture, uri, mimetype, finish_func, media)
    if parent_type is Gtk.Overlay:
        shortcuts = Gtk.ShortcutController()
        parent.add_controller(shortcuts)
        add_grab_focus(parent)
        if mimetype.startswith("video"): shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("space"), Gtk.CallbackAction.new(media_play_pause)))
        if not scrollable == None:
            shortcuts.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("f"), Gtk.CallbackAction.new(lambda w, *_: (w.get_child().get_child().set_vscroll_policy(not w.get_child().get_child().get_vscroll_policy()), True)[-1] )))
        add_move_shortcuts(shortcuts, scrolled if not scrollable == None else parent)
    return parent
toggle_revealer = lambda b, v: True if hasattr(b.get_property("target"), "controls") and b.get_property("target").controls.get_template_child(Gtk.MediaControls, "volume_button").get_active() else v
def media_play_pause(parent: Gtk.Widget, *_) -> None:
    child = parent.get_child()
    if isinstance(parent.get_child(), Gtk.ScrolledWindow):
        child = child.get_child().get_child()
    child.get_paintable().set_playing(False if child.get_paintable().get_playing() else True)
def load_image(picture: Gtk.Picture, uri: Gio.File | None | str, mimetype="", finish_func=default_finish, media=False) -> None:
    if isinstance(uri, str):
        uri = Gio.File.new_for_uri(uri)
    if uri and not mimetype:
        mimetype = Gio.content_type_guess(uri.get_uri())[0]
    try:
        if uri.get_uri().startswith("file://"):
            if mimetype.endswith("zip"):
                z = ZipFile(uri.peek_path(), "r")
                i = sorted((i for i in z.namelist() if Gio.content_type_guess(i)[0].startswith("image")), key=alphabetical_sort)
                stream = Gio.MemoryInputStream.new_from_data(z.read(i[0]))
            else:
                stream = uri.read()
        else:
            stream = app.session.send(Soup.Message.new("GET", uri.get_uri()))
    except Exception as e:
        Toast(e)
        return GLib.idle_add(picture.set_tooltip_text, str(e))
    if GLY:
        image = Gly.Loader.new_for_stream(stream).load()
        frame = image.next_frame()
        texture = GlyGtk4.frame_get_texture(frame)
        picture.height = image.get_height() / image.get_width()
        if frame.get_delay() > 0:
            if media:
                picture.media = Gtk.MediaFile.new_for_file(uri)
                picture.sig = picture.media.connect("invalidate-contents", media_finish, (picture, finish_func))
                picture.media.set_properties(playing=True, loop=True)
                return
            else:
                picture.image = image
                picture.connect("map", media_image_animate)
        GLib.idle_add(picture.set_paintable if hasattr(picture, "set_paintable") else picture.set_custom_image, texture)
        GLib.idle_add(picture.remove_css_class, "spinner")
        finish_func(picture, texture)
    else:
        pixbuf = Gdk.Pixbuf.PixbufAnimation.new_from_stream(stream)
        picture.height = pixbuf.get_height() / pixbuf.get_width()
        if pixbuf.is_static_image():
            if hasattr(picture, "set_pixbuf"): GLib.idle_add(picture.set_pixbuf, pixbuf.get_static_image())
            else: GLib.idle_add(picture.set_custom_image, Gdk.Texture.new_for_pixbuf(pixbuf.get_static_image()))
        else:
            picture.image = pixbuf.get_iter()
            picture.connect("map", media_image_animate)
        GLib.idle_add(picture.remove_css_class, "spinner")
        finish_func(picture, pixbuf)
def media_finish(paintable: Gtk.MediaFile, data: tuple) -> None:
    paintable.disconnect(data[0].sig)
    GLib.idle_add(data[0].remove_css_class, "spinner")
    GLib.idle_add(data[0].set_paintable if hasattr(data[0], "set_paintable") else data[0].set_custom_image, paintable)
    data[1](data[0], paintable)
    del data[0].media
def media_image_animate(p: Gtk.Picture, *_) -> None:
    if p.get_mapped():
        if isinstance(p.image, GdkPixbuf.PixbufAnimationIter):
            delay = p.image.get_delay_time()
            if p.image.advance():
                if hasattr(p, "set_pixbuf"): GLib.idle_add(p.set_pixbuf, p.image.get_pixbuf())
                else: GLib.idle_add(p.set_custom_image, Gdk.Texture.new_for_pixbuf(p.image.get_pixbuf()))
        else:
            f = p.image.next_frame()
            delay = f.get_delay() / 1000
            GLib.idle_add(p.set_paintable if hasattr(p, "set_paintable") else p.set_custom_image, GlyGtk4.frame_get_texture(f))
        GLib.timeout_add(delay, media_image_animate, p)
def set_colors(arg=None, optional=False) -> False:
    if hasattr(arg, "colors") and not (optional and not app.lookup_action("colors").get_state().unpack()):
        style = Gtk.CssProvider()
        GLib.idle_add(style.load_from_string, ":root {" + "".join(tuple(f"--color-{i + 1}: rgb{color};" for i, color in enumerate(arg.colors))) + "}")
        GLib.idle_add(Gtk.StyleContext.add_provider_for_display, *(Gdk.Display.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_USER))
        GLib.idle_add(app.window.add_css_class, "colored")
    else: GLib.idle_add(app.window.remove_css_class, "colored")
    return False

def add_move_shortcuts(controller: Gtk.ShortcutController, scrolled: bool) -> None:
    for i in ("Up", "w", "k"): GLib.idle_add(controller.add_shortcut, Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(i), Gtk.CallbackAction.new(scroll_move_shortcuts, Gtk.DirectionType.UP, scrolled)))
    for i in ("Down", "s", "j"): GLib.idle_add(controller.add_shortcut, Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(i), Gtk.CallbackAction.new(scroll_move_shortcuts, Gtk.DirectionType.DOWN, scrolled)))
    for i in ("Left", "a", "h"): GLib.idle_add(controller.add_shortcut, Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(i), Gtk.CallbackAction.new(scroll_move_shortcuts, Gtk.DirectionType.LEFT, scrolled)))
    for i in ("Right", "d", "l"): GLib.idle_add(controller.add_shortcut, Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(i), Gtk.CallbackAction.new(scroll_move_shortcuts, Gtk.DirectionType.RIGHT, scrolled)))
def scroll_move_shortcuts(widget: Gtk.Widget, args: None, direction: Gtk.DirectionType, scrolled: bool) -> bool:
    policy, invert = None, False
    if scrolled:
        viewport = widget
        while not isinstance(viewport, Gtk.Viewport):
            viewport = viewport.get_child()
        policy = viewport.get_hscroll_policy() if direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT) else viewport.get_vscroll_policy()
        if policy is Gtk.ScrollablePolicy.NATURAL:
            adjustment = viewport.get_hadjustment() if direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT) else viewport.get_vadjustment()
        else:
            adjustment = None
    controls = widget.controls if hasattr(widget, "controls") else widget.get_parent().controls if hasattr(widget.get_parent(), "controls") else None
    if not policy is Gtk.ScrollablePolicy.NATURAL:
        if controls:
            t = "volume_button" if direction in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN) else "seek_scale"
            adjustment = controls.get_template_child(Gtk.MediaControls, t).get_adjustment()
            invert = t == "volume_button"
    if not adjustment: return False
    if invert:
        v = -(adjustment.get_step_increment()) if direction in (Gtk.DirectionType.RIGHT, Gtk.DirectionType.DOWN) else adjustment.get_step_increment()
    else:
        v = adjustment.get_step_increment() if direction in (Gtk.DirectionType.RIGHT, Gtk.DirectionType.DOWN) else -(adjustment.get_step_increment())
    adjustment.set_value(v + adjustment.get_value())
    return True

def MasonryBox(adapt=((999, 2, Adw.BreakpointConditionLengthType.MAX_WIDTH), (1000, 3, Adw.BreakpointConditionLengthType.MIN_WIDTH), (1200, 4, Adw.BreakpointConditionLengthType.MIN_WIDTH)), activate=None) -> Adw.BreakpointBin:
    box = Gtk.Box(css_name="view", homogeneous=True)
    for _ in range(max((i[1] for i in adapt))): box.append(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_name="column", valign=Gtk.Align.START))
    masonrybox = Adw.BreakpointBin(focusable=True, child=Gtk.ScrolledWindow(child=Gtk.Viewport(child=box, scroll_to_focus=False, vscroll_policy=Gtk.ScrollablePolicy.NATURAL), hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_width=True), width_request=1, height_request=1, css_name="masonrybox")
    masonrybox.connect("notify::width-request", masonrybox_update)
    for v, c, t in adapt:
        b = Adw.Breakpoint.new(Adw.BreakpointCondition.new_length(t, v, Adw.LengthUnit.PX))
        b.add_setter(masonrybox, "width-request", c)
        masonrybox.add_breakpoint(b)
    masonrybox.add = lambda c: masonrybox_add(masonrybox, c)
    masonrybox.remove = lambda c: tuple(i.unparent() if i == c else None for i in masonrybox.get_children())
    masonrybox.remove_all = lambda clear=True: masonrybox_remove_all(masonrybox, clear)
    masonrybox.get_children = lambda: sorted((i for c in masonrybox.get_child().get_child().get_child() for i in c if c.get_visible()), key=lambda i: i.__pos)
    if activate:
        masonrybox.activate = activate
        for n in range(3): masonrybox.add_controller((g := Gtk.GestureClick(button=n + 1), g.connect("released", masonrybox_activate), g)[-1])
    c = Gtk.ShortcutController()
    masonrybox.add_controller(c)
    add_move_shortcuts(c, True)
    add_grab_focus(masonrybox)
    return masonrybox
def masonrybox_update(m: Adw.BreakpointBin, param: GObject.ParamSpec) -> None:
    for c in sorted(m.remove_all(clear=False), key=lambda i: i.__pos): m.add(c)
def masonrybox_activate(g: Gtk.GestureClick, n_press:int, x: float, y: float) -> None:
    g.get_widget().grab_focus()
    child = g.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
    if not child: return
    if child.get_parent() in (g.get_widget().get_child(), g.get_widget().get_child().get_child(), g.get_widget().get_child().get_child().get_child()): return
    while child not in g.get_widget().get_children():
        child = child.get_parent()
    g.get_widget().activate(g.get_widget(), child, g.get_button())
def masonrybox_add(masonrybox: Adw.BreakpointBin, child: Gtk.Widget) -> None:
    child.unparent()
    child.__pos = max((i.__pos for i in masonrybox.get_children()), default=0) + 1
    for i in masonrybox.get_child().get_child().get_child():
        i.height = sum((it.height if hasattr(it, "height") else max(10, it.get_height()) / max(10, it.get_width()) for it in i))
    box = masonrybox.get_child().get_child().get_child()
    min(tuple(i for i in box if i.get_visible()), key=lambda i: i.height, default=box.get_first_child()).append(child)
def masonrybox_remove_all(masonrybox: Adw.BreakpointBin, clear: bool) -> None | tuple:
    children = masonrybox.get_children()
    for child in children: child.unparent()
    box = masonrybox.get_child().get_child().get_child()
    for i, c in enumerate(box): c.set_visible(masonrybox.get_property("width-request") > i)
    for i in masonrybox.get_child().get_child().get_child():
        i.height = sum((it.height if hasattr(it, "height") else max(10, it.get_height()) / max(10, it.get_width()) for it in i))
    return None if clear else children    

def EntryDialog(callback=None, multiline=False, appearance=Adw.ResponseAppearance.SUGGESTED, **kwargs) -> Adw.AlertDialog:
    dialog = Adw.AlertDialog(extra_child=Gtk.TextView() if multiline else Gtk.Entry(), **kwargs)
    dialog.add_css_class("entry-dialog")
    key = Gtk.EventControllerKey()
    key.connect("key-pressed", lambda e, kv, *_: (e.get_widget().get_ancestor(Adw.Dialog).close(), True)[-1] if kv == Gdk.KEY_Escape else False)
    dialog.get_extra_child().add_controller(key)
    if callback: dialog.connect("response", lambda d, r: callback(d) if r == "confirm" else None)
    if not multiline: dialog.get_extra_child().connect("activate", lambda e: (e.get_ancestor(Adw.Dialog).emit("response", "confirm"), e.get_ancestor(Adw.Dialog).close()))
    for i in ("cancel", "confirm"): dialog.add_response(i, i.title())
    dialog.set_response_appearance("confirm", appearance)
    dialog.connect("map", lambda d: (d.get_extra_child().set_text("") if isinstance(d.get_extra_child(), Gtk.Entry) else d.get_extra_child().get_buffer().set_text(""), d.get_extra_child().grab_focus())[0] if d.get_mapped() else None)
    return dialog

def DateRow(**kwargs) -> Adw.ActionRow:
    row = Adw.ActionRow(**kwargs, css_classes=("property", "date-row"), subtitle_selectable=True)
    row.calendar = calendar = Gtk.Calendar()
    calendar.bind_property("date", row, "subtitle", GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE, lambda b, v: v.format("%x"))
    row.add_suffix(Button(t=Gtk.MenuButton, css_classes=("flat",), icon_name="month", popover=Gtk.Popover(child=calendar), valign=Gtk.Align.CENTER, tooltip_text="Pick a Date"))
    return row

def data_default(existing: dict, data: dict) -> None:
    for key in data:
        existing.setdefault(key, data[key])
        if isinstance(data[key], dict): data_default(existing[key], data[key])

def data_save() -> None:
    for i in app.data["Window"]:
        app.data["Window"][i] = app.lookup_action(i).get_state().unpack()
    for i in app.persist:
        if isinstance(i, Gio.Action):
            app.data[i.path][i.get_name()] = i.get_state().unpack()
        else:
            n = i.get_title() if hasattr(i, "get_title") else i.get_name()
            v = i.get_property(i.property)
            if hasattr(i, "page"):
                app.data[i.page][i.group][n] = v.unpack() if hasattr(v, "unpack") else v.get_string() if hasattr(v, "get_string") else v
            else:
                app.data[i.path][n] = v.unpack() if hasattr(v, "unpack") else v.get_string() if hasattr(v, "get_string") else v
    app.data_file.replace_contents(marshal_string(app.data), None, True, 0)

def launch(arg: Gio.File | str, folder=False) -> None:
    if isinstance(arg, Gio.File) or folder:
        if not isinstance(arg, Gio.File):
            arg = Gio.File.new_for_path(arg)
        app.file_launcher.set_file(arg)
        if folder: app.file_launcher.open_containing_folder()
        else: app.file_launcher.launch()
    else:
        app.uri_launcher.set_uri(arg)
        app.uri_launcher.launch()

def generate_thumbnail(file: Gio.File | str, destination: Gio.File | str, callback=None, data=None) -> None:
    f, d = file.peek_path() if isinstance(file, Gio.File) else file, destination.peek_path() if isinstance(destination, Gio.File) else destination
    process = Gio.Subprocess.new(("ffmpeg", "-v", "quiet", "-i", f, "-vf", r"thumbnail,scale=if(gte(iw\,ih)\,min(720\,iw)\,-2):if(lt(iw\,ih)\,min(720\,ih)\,-2)", "-frames:v", "1", d), Gio.SubprocessFlags.NONE)
    if callback: process.wait_async(None, callback, data)
    else: process.wait()

def palette(value: Gdk.Paintable | GdkPixbuf.Pixbuf, colors=3, distance=1.0, black_white=1.0) -> list:
    if hasattr(value, "get_media_stream"):
        value = value.get_media_stream()
    if hasattr(value, "get_paintable"):
        value = value.get_paintable()
    if hasattr(value, "get_static_image"):
        value = value.get_static_image()
    if not isinstance(value, Gdk.Texture) and hasattr(value, "snapshot"):
        snapshot = Gtk.Snapshot.new()
        s, w, h = 64, value.get_intrinsic_width(), value.get_intrinsic_height()
        if max(w, h) > s:
            s = s / max(w, h)
            w, h = int(w * s), int(h * s)
        value.snapshot(snapshot, w, h)
        value = snapshot.to_node().get_texture()
    if isinstance(value, Gdk.Texture):
        value = Gdk.pixbuf_get_from_texture(value)
    s, w, h = 64, value.get_width(), value.get_height()
    if max(w, h) > s:
        s = s / max(w, h)
        value = value.scale_simple(int(w * s), int(h * s), 2)
    pixel_colors = {}
    pixels = value.get_property("pixel-bytes").get_data()
    for y in range(value.get_height()):
        for x in range(value.get_width()):
            if value.get_has_alpha():
                i = y * value.get_rowstride() + x * 4
                if 120 > pixels[i + 3]: continue
            else:
                i = y * value.get_rowstride() + x * 3
            color = (pixels[i], pixels[i + 1], pixels[i + 2])
            pixel_colors[color] = pixel_colors.get(color, 1) + 1
    pixel_colors = tuple(i[0] for i in sorted(pixel_colors.items(), key=itemgetter(1), reverse=True))
    dominant_colors = list()
    current_distance = 0
    while colors > len(dominant_colors):
        current_length = len(dominant_colors)
        for color in pixel_colors:
            if color in dominant_colors or sqrt(sum(c ** 2 for c in color)) < max(0, int(black_white * 100) - current_distance) or sqrt(sum((255 - i) ** 2 for i in color)) < max(0, int(black_white * 100) - current_distance): continue
            too_similar = False
            for selected_color in dominant_colors:
                if sqrt(sum((c1 - c2) ** 2 for c1, c2 in zip(color, selected_color))) < int(distance * 100) - current_distance:
                    too_similar = True
                    break
            if not too_similar: dominant_colors.append(color)
            if len(dominant_colors) >= colors: break
        if current_length == len(dominant_colors):
            current_distance += 5
    return dominant_colors

random_sort = lambda c: GLib.random_int_range(1, 500)
alphabetical_sort = lambda e: GLib.utf8_collate_key_for_filename(e.peek_path() if isinstance(e, Gio.File) else e, -1)

def add_grab_focus(w: Gtk.Widget) -> None:
    w.set_focusable(True)
    click = Gtk.GestureClick()
    click.connect("pressed", lambda e, *_: e.get_widget().grab_focus())
    w.add_controller(click)
