from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gd
from gi.repository import Grl
from gi.repository import Pango
from gi.repository import GLib
from gi.repository import GdkPixbuf
from gi.repository import Tracker
from gnomemusic.grilo import grilo
import gnomemusic.widgets as Widgets
from gnomemusic.query import Query
from gnomemusic.albumArtCache import AlbumArtCache as albumArtCache
tracker = Tracker.SparqlConnection.get(None)


def extractFileName(uri):
    exp = "^.*[\\\/]|[.][^.]*$"
    return uri.replace(exp, '')


class ViewContainer(Gtk.Stack):
    nowPlayingIconName = 'media-playback-start-symbolic'
    errorIconName = 'dialog-error-symbolic'
    starIconName = 'starred-symbolic'
    countQuery = None

    def __init__(self, title, header_bar, selection_toolbar, useStack=False):
        Gtk.Stack.__init__(self,
                           transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self._iconWidth = -1
        self._iconHeight = 128
        self._offset = 0
        self._adjustmentValueId = 0
        self._adjustmentChangedId = 0
        self._scrollbarVisibleId = 0
        self._model = Gtk.ListStore.new([
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GdkPixbuf.Pixbuf,
            GObject.TYPE_OBJECT,
            GObject.TYPE_BOOLEAN,
            GObject.TYPE_INT,
            GObject.TYPE_STRING,
            GObject.TYPE_BOOLEAN,
            GObject.TYPE_BOOLEAN
        ])
        self.view = Gd.MainView(
            shadow_type=Gtk.ShadowType.NONE
        )
        self.view.set_view_type(Gd.MainViewType.ICON)
        self.view.set_model(self._model)
        self.selection_toolbar = selection_toolbar
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.view, True, True, 0)
        if useStack:
            self.stack = Gd.Stack(
                transition_type=Gd.StackTransitionType.SLIDE_RIGHT,
            )
            dummy = Gtk.Frame(visible=False)
            self.stack.add_named(dummy, "dummy")
            self.stack.add_named(box, "artists")
            self.stack.set_visible_child_name("dummy")
            self._grid.add(self.stack)
        else:
            self._grid.add(box)

        self._loadMore = Widgets.LoadMoreButton(self._get_remaining_item_count)
        box.pack_end(self._loadMore.widget, False, False, 0)
        self._loadMore.widget.connect("clicked", self._populate)
        self.view.connect('item-activated', self._on_item_activated)
        self._cursor = None
        self.header_bar = header_bar
        self.header_bar._selectButton.connect(
            'toggled', self._on_header_bar_toggled)
        self.header_bar._cancelButton.connect(
            'clicked', self._on_cancel_button_clicked)

        self.title = title
        self.add(self._grid)

        self.show_all()
        self._items = []
        self._loadMore.widget.hide()
        self._connect_view()
        self.cache = albumArtCache.get_default()
        self._symbolicIcon = self.cache.make_default_icon(self._iconHeight,
                                                          self._iconWidth)

        self._init = False
        grilo.connect('ready', self._on_grilo_ready)
        self.header_bar.header_bar.connect('state-changed',
                                           self._on_state_changed)
        self.view.connect('view-selection-changed',
                          self._on_view_selection_changed)

    def _on_header_bar_toggled(self, button):
        if button.get_active():
            self.view.set_selection_mode(True)
            self.header_bar.set_selection_mode(True)
            self.selection_toolbar.eventbox.set_visible(True)
            self.selection_toolbar._add_to_playlist_button.sensitive = False
        else:
            self.view.set_selection_mode(False)
            self.header_bar.set_selection_mode(False)
            self.selection_toolbar.eventbox.set_visible(False)

    def _on_cancel_button_clicked(self, button):
        self.view.set_selection_mode(False)
        self.header_bar.set_selection_mode(False)

    def _on_grilo_ready(self, data=None):
        if (self.header_bar.get_stack().get_visible_child() == self
                and not self._init):
            self._populate()
        self.header_bar.get_stack().connect('notify::visible-child',
                                            self._on_headerbar_visible)

    def _on_headerbar_visible(self, widget, param):
        if self == widget.get_visible_child() and not self._init:
            self._populate()

    def _on_view_selection_changed(self, widget):
        items = self.view.get_selection()
        self.selection_toolbar._add_to_playlist_button.set_sensitive(len(items) > 0)

    def _populate(self, data=None):
        self._init = True
        self.populate()

    def _on_state_changed(self, widget, data=None):
        pass

    def _connect_view(self):
        vadjustment = self.view.get_vadjustment()
        self._adjustmentValueId = vadjustment.connect(
            'value-changed',
            self._on_scrolled_win_change)

    def _on_scrolled_win_change(self, data=None):
        vScrollbar = self.view.get_vscrollbar()
        adjustment = self.view.get_vadjustment()
        revealAreaHeight = 32

        #if there's no vscrollbar, or if it's not visible, hide the button
        if not vScrollbar or not vScrollbar.get_visible():
            self._loadMore.set_block(True)
            return

        value = adjustment.get_value()
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()

        end = False
        #special case self values which happen at construction
        if (value == 0) and (upper == 1) and (page_size == 1):
            end = False
        else:
            end = not (value < (upper - page_size - revealAreaHeight))
        if self._get_remaining_item_count() <= 0:
            end = False
        self._loadMore.set_block(not end)

    def populate(self):
        print("populate")

    def _add_item(self, source, param, item):
        if item is not None:
            self._offset += 1
            iter = self._model.append()
            artist = "Unknown"
            if item.get_author() is not None:
                artist = item.get_author()
            if item.get_string(Grl.METADATA_KEY_ARTIST) is not None:
                artist = item.get_string(Grl.METADATA_KEY_ARTIST)
            if (item.get_title() is None) and (item.get_url() is not None):
                item.set_title(extractFileName(item.get_url()))
            try:
                if item.get_url():
                    self.player.discoverer.discover_uri(item.get_url())
                self._model.set(iter,
                                [0, 1, 2, 3, 4, 5, 7, 8, 9, 10],
                                [str(item.get_id()), "", item.get_title(),
                                 artist, self._symbolicIcon, item,
                                 -1, self.nowPlayingIconName, False, False])
            except:
                print("failed to discover url " + item.get_url())
                self._model.set(iter,
                                [0, 1, 2, 3, 4, 5, 7, 8, 9, 10],
                                [str(item.get_id()), "", item.get_title(),
                                 artist, self._symbolicIcon, item,
                                 -1, self.errorIconName, False, True])
            GLib.idle_add(self._update_album_art, item, iter)

    def _get_remaining_item_count(self):
        count = -1
        if self.countQuery is not None:
            cursor = tracker.query(self.countQuery, None)
            if cursor is not None and cursor.next(None):
                count = cursor.get_integer(0)
        return count - self._offset

    def _update_album_art(self, item, iter):
        def _album_art_cache_look_up(icon, data=None):
            if icon:
                self._model.set_value(
                    iter, 4,
                    albumArtCache.get_default()._make_icon_frame(icon))
            else:
                self._model.set_value(iter, 4, None)
                self.emit("album-art-updated")
            pass

        albumArtCache.get_default().lookup_or_resolve(item,
                                                      self._iconWidth,
                                                      self._iconHeight,
                                                      _album_art_cache_look_up)
        return False

    def _add_list_renderers(self):
        pass

    def _on_item_activated(self, widget, id, path):
        pass


#Class for the Empty View
class Empty(Gtk.Stack):
    def __init__(self, header_bar, player):
        Gtk.Stack.__init__(self,
                           transition_type=Gtk.StackTransitionType.CROSSFADE)
        builder = Gtk.Builder()
        builder.add_from_resource('/org/gnome/music/NoMusic.ui')
        widget = builder.get_object('container')
        self.add(widget)
        self.show_all()


class Albums(ViewContainer):
    def __init__(self, header_bar, selection_toolbar, player):
        ViewContainer.__init__(self, "Albums", header_bar, selection_toolbar)
        self.view.set_view_type(Gd.MainViewType.ICON)
        self.countQuery = Query.ALBUMS_COUNT
        self._albumWidget = Widgets.AlbumWidget(player)
        self.add(self._albumWidget)

    def _back_button_clicked(self, widget, data=None):
        self.set_visible_child(self._grid)

    def _on_item_activated(self, widget, id, path):
        iter = self._model.get_iter(path)
        title = self._model.get_value(iter, 2)
        artist = self._model.get_value(iter, 3)
        item = self._model.get_value(iter, 5)
        self._albumWidget.update(artist, title, item,
                                 self.header_bar, self.selection_toolbar)
        self.header_bar.set_state(0)
        self.header_bar.header_bar.title = title
        self.header_bar.header_bar.set_title(title)
        self.header_bar.header_bar.sub_title = artist
        self.set_visible_child(self._albumWidget)

    def populate(self):
        if grilo.tracker is not None:
            grilo.populate_albums(self._offset, self._add_item)


class Songs(ViewContainer):
    def __init__(self, header_bar, selection_toolbar, player):
        ViewContainer.__init__(self, "Songs", header_bar, selection_toolbar)
        self.countQuery = Query.SONGS_COUNT
        self._items = {}
        self.isStarred = None
        self.view.set_view_type(Gd.MainViewType.LIST)
        self.view.get_generic_view().get_style_context()\
            .add_class("songs-list")
        self._iconHeight = 32
        self._iconWidth = 32
        self.cache = albumArtCache.get_default()
        self._symbolicIcon = self.cache.make_default_icon(self._iconHeight,
                                                          self._iconWidth)
        self._add_list_renderers()
        self.player = player
        self.player.connect('playlist-item-changed', self.update_model)

    def _on_item_activated(self, widget, id, path):
        iter = self._model.get_iter(path)[1]
        if self._model.get_value(iter, 8) != self.errorIconName:
            self.player.set_playlist("Songs", None, self._model, iter, 5)
            self.player.set_playing(True)

    def update_model(self, player, playlist, currentIter):
        if playlist != self._model:
            return False
        if self.iterToClean:
            self._model.set_value(self.iterToClean, 10, False)

        self._model.set_value(currentIter, 10, True)
        self.iterToClean = currentIter.copy()
        return False

    def _add_item(self, source, param, item):
        if item is not None:
            self._offset += 1
            iter = self._model.append()
            if (item.get_title() is None) and (item.get_url() is not None):
                item.set_title(extractFileName(item.get_url()))
            try:
                if item.get_url():
                    self.player.discoverer.discover_uri(item.get_url())
                self._model.set(iter,
                                [5, 8, 9, 10],
                                [item, self.nowPlayingIconName, False, False])
            except:
                print("failed to discover url " + item.get_url())
                self._model.set(iter,
                                [5, 8, 9, 10],
                                [item, self.errorIconName, False, True])

    def _add_list_renderers(self):
        listWidget = self.view.get_generic_view()
        cols = listWidget.get_columns()
        cells = cols[0].get_cells()
        cells[2].visible = False
        nowPlayingSymbolRenderer = Gtk.CellRendererPixbuf()
        columnNowPlaying = Gtk.TreeViewColumn()
        nowPlayingSymbolRenderer.xalign = 1.0
        columnNowPlaying.pack_start(nowPlayingSymbolRenderer, False)
        columnNowPlaying.fixed_width = 24
        columnNowPlaying.add_attribute(nowPlayingSymbolRenderer,
                                       "visible", 10)
        columnNowPlaying.add_attribute(nowPlayingSymbolRenderer,
                                       "icon_name", 8)
        listWidget.insert_column(columnNowPlaying, 0)

        titleRenderer = Gtk.CellRendererText(xpad=0)
        listWidget.add_renderer(titleRenderer,
                                self._on_list_widget_title_render, None)
        starRenderer = Gtk.CellRendererPixbuf(xpad=32)
        listWidget.add_renderer(starRenderer,
                                self._on_list_widget_star_render, None)
        durationRenderer = Gd.StyledTextRenderer(xpad=32)
        durationRenderer.add_class('dim-label')
        listWidget.add_renderer(durationRenderer,
                                self._on_list_widget_duration_render, None)
        artistRenderer = Gd.StyledTextRenderer(xpad=32)
        artistRenderer.add_class('dim-label')
        artistRenderer.ellipsize = Pango.EllipsizeMode.END
        listWidget.add_renderer(artistRenderer,
                                self._on_list_widget_artist_render, None)
        typeRenderer = Gd.StyledTextRenderer(xpad=32)
        typeRenderer.add_class('dim-label')
        typeRenderer.ellipsize = Pango.EllipsizeMode.END
        listWidget.add_renderer(typeRenderer,
                                self._on_list_widget_type_render, None)

    def _on_list_widget_title_render(self, col, cell, model, itr, data):
        item = model.get_value(itr, 5)
        cell.xalign = 0.0
        cell.yalign = 0.5
        cell.height = 48
        cell.ellipsize = Pango.EllipsizeMode.END
        cell.text = item.get_title()

    def _on_list_widget_star_render(self, col, cell, model, itr, data):
        showstar = model.get_value(itr, 9)
        if(showstar):
            cell.icon_name = self.starIconName
        else:
            cell.pixbuf = None

    def _on_list_widget_duration_render(self, col, cell, model, itr, data):
        item = model.get_value(itr, 5)
        if item:
            duration = item.get_duration()
            minutes = int(duration / 60)
            seconds = duration % 60
            cell.xalign = 1.0
            cell.text = "%i:%02i" % (minutes, seconds)

    def _on_list_widget_artist_render(self, col, cell, model, itr, data):
        item = model.get_value(itr, 5)
        if item:
            cell.ellipsize = Pango.EllipsizeMode.END
            cell.text = item.get_string(Grl.METADATA_KEY_ARTIST)

    def _on_list_widget_type_render(self, coll, cell, model, itr, data):
        item = model.get_value(itr, 5)
        if item:
            cell.ellipsize = Pango.EllipsizeMode.END
            cell.text = item.get_string(Grl.METADATA_KEY_ALBUM)

    def populate(self):
        if grilo.tracker is not None:
            grilo.populate_songs(self._offset, self._add_item)


class Playlist(ViewContainer):
    def __init__(self, header_bar, selection_toolbar, player):
        ViewContainer.__init__(self, "Playlists", header_bar,
                               selection_toolbar)


class Artists (ViewContainer):
    def __init__(self, header_bar, selection_toolbar, player):
        ViewContainer.__init__(self, "Artists", header_bar,
                               selection_toolbar, True)
        self.player = player
        self._artists = {}
        self.countQuery = Query.ARTISTS_COUNT
        self._artistAlbumsWidget = Gtk.Frame(
            shadow_type=Gtk.ShadowType.NONE
        )
        self.view.set_view_type(Gd.MainViewType.LIST)
        self.view.set_hexpand(False)
        self._artistAlbumsWidget.set_hexpand(True)
        self.view.get_style_context().add_class("artist-panel")
        self.view.get_generic_view().get_selection().set_mode(
            Gtk.SelectionMode.SINGLE)
        self._grid.attach(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                          1, 0, 1, 1)
        self._grid.attach(self._artistAlbumsWidget, 2, 0, 2, 2)
        self._add_list_renderers()
        if (Gtk.Settings.get_default().get_property(
                'gtk_application_prefer_dark_theme')):
            self.view.get_generic_view().get_style_context().\
                add_class("artist-panel-dark")
        else:
            self.view.get_generic_view().get_style_context().\
                add_class("artist-panel-white")
        self.show_all()

    def _populate(self, data=None):
        selection = self.view.get_generic_view().get_selection()
        if not selection.get_selected()[1]:
            self._allIter = self._model.append()
            self._artists["All Artists".lower()] =\
                {"iter": self._allIter, "albums": []}
            self._model.set(
                self._allIter,
                [0, 1, 2, 3],
                ["All Artists", "All Artists", "All Artists", "All Artists"]
            )
            selection.select_path(self._model.get_path(self._allIter))
            self.view.emit('item-activated', "0",
                           self._model.get_path(self._allIter))
        self._init = True
        self.populate()

    def _add_list_renderers(self):
        listWidget = self.view.get_generic_view()

        cols = listWidget.get_columns()
        cells = cols[0].get_cells()
        cells[2].visible = False

        typeRenderer = Gd.StyledTextRenderer(xpad=0)
        typeRenderer.ellipsize = 3
        typeRenderer.xalign = 0.0
        typeRenderer.yalign = 0.5
        typeRenderer.height = 48
        typeRenderer.width = 220

        def type_render(self, cell, model, itr, data):
            typeRenderer.text = model.get_value(itr, 0)

        listWidget.add_renderer(typeRenderer, type_render, None)

    def _on_item_activated(self, widget, item_id, path):
        children = self._artistAlbumsWidget.get_children()
        for child in children:
            self._artistAlbumsWidget.remove(child)
        itr = self._model.get_iter(path)
        artist = self._model.get_value(itr, 0)
        albums = self._artists[artist.lower()]["albums"]
        self.artistAlbums = None
        if (self._model.get_string_from_iter(itr) ==
                self._model.get_string_from_iter(self._allIter)):
            self.artistAlbums = Widgets.AllArtistsAlbums(self.player)
        else:
            self.artistAlbums = Widgets.ArtistAlbums(artist, albums,
                                                     self.player)
        self._artistAlbumsWidget.add(self.artistAlbums)

    def _add_item(self, source, param, item):
        self._offset += 1
        if item is None:
            return
        artist = "Unknown"
        if item.get_author() is not None:
            artist = item.get_author()
        if item.get_string(Grl.METADATA_KEY_ARTIST) is not None:
            artist = item.get_string(Grl.METADATA_KEY_ARTIST)
        if not artist.lower() in self._artists:
            itr = self._model.append()
            self._artists[artist.lower()] = {"iter": itr, "albums": []}
            self._model.set(
                itr,
                [0, 1, 2, 3],
                [artist, artist, artist, artist]
            )

        self._artists[artist.lower()]["albums"].append(item)
        #FIXME: add new signal
        #self.emit("artist-added")

    def populate(self):
        if grilo.tracker is not None:
            grilo.populate_artists(self._offset, self._add_item)
            #FIXME: We're emitting self too early,
            #need to wait for all artists to be filled in