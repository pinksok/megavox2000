"""MPRIS D-Bus service for Bluetooth hardware button support."""

import subprocess

import state
from player import toggle_pause_internal, stop_player


def mpris_thread_func():
    """Run MPRIS D-Bus service so mpris-proxy can relay BT button presses."""
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    MPRIS_IFACE = "org.mpris.MediaPlayer2"
    PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
    PROPS_IFACE = "org.freedesktop.DBus.Properties"

    class YTMusicMPRIS(dbus.service.Object):
        def __init__(self, bus):
            name = dbus.service.BusName("org.mpris.MediaPlayer2.turbovox2000", bus)
            super().__init__(name, "/org/mpris/MediaPlayer2")
            self._playback_status = "Stopped"

        # -- org.mpris.MediaPlayer2 --
        @dbus.service.method(MPRIS_IFACE)
        def Raise(self):
            pass

        @dbus.service.method(MPRIS_IFACE)
        def Quit(self):
            pass

        # -- org.mpris.MediaPlayer2.Player --
        @dbus.service.method(PLAYER_IFACE)
        def Play(self):
            print("[MPRIS] Play received", flush=True)
            if state.paused:
                toggle_pause_internal()

        @dbus.service.method(PLAYER_IFACE)
        def Pause(self):
            print("[MPRIS] Pause received", flush=True)
            if not state.paused:
                toggle_pause_internal()

        @dbus.service.method(PLAYER_IFACE)
        def PlayPause(self):
            print("[MPRIS] PlayPause received", flush=True)
            toggle_pause_internal()

        @dbus.service.method(PLAYER_IFACE)
        def Stop(self):
            print("[MPRIS] Stop received", flush=True)
            stop_player()

        @dbus.service.method(PLAYER_IFACE)
        def Next(self):
            pass

        @dbus.service.method(PLAYER_IFACE)
        def Previous(self):
            pass

        # -- Properties --
        @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            if interface == PLAYER_IFACE:
                if prop == "PlaybackStatus":
                    return self._playback_status
                if prop == "CanPlay":
                    return True
                if prop == "CanPause":
                    return True
                if prop == "CanGoNext":
                    return False
                if prop == "CanGoPrevious":
                    return False
                if prop == "CanSeek":
                    return False
                if prop == "CanControl":
                    return True
                if prop == "Metadata":
                    return dbus.Dictionary({
                        "mpris:trackid": dbus.ObjectPath("/org/mpris/MediaPlayer2/Track/1"),
                        "xesam:title": state.current_title or "TurboVox 2000",
                    }, signature="sv")
            if interface == MPRIS_IFACE:
                if prop == "Identity":
                    return "TurboVox 2000 Player"
                if prop == "CanQuit":
                    return False
                if prop == "CanRaise":
                    return False
                if prop == "HasTrackList":
                    return False
            return ""

        @dbus.service.method(PROPS_IFACE, in_signature="ssv")
        def Set(self, interface, prop, value):
            if interface == PLAYER_IFACE and prop == "PlaybackStatus":
                self._playback_status = str(value)

        @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface == PLAYER_IFACE:
                return {
                    "PlaybackStatus": self._playback_status,
                    "CanPlay": True,
                    "CanPause": True,
                    "CanGoNext": False,
                    "CanGoPrevious": False,
                    "CanSeek": False,
                    "CanControl": True,
                    "Metadata": dbus.Dictionary({
                        "mpris:trackid": dbus.ObjectPath("/org/mpris/MediaPlayer2/Track/1"),
                        "xesam:title": state.current_title or "TurboVox 2000",
                    }, signature="sv"),
                }
            if interface == MPRIS_IFACE:
                return {
                    "Identity": "TurboVox 2000 Player",
                    "CanQuit": False,
                    "CanRaise": False,
                    "HasTrackList": False,
                }
            return {}

    bus = dbus.SessionBus()
    player = YTMusicMPRIS(bus)
    print("[MPRIS] Registered on D-Bus", flush=True)

    # Start mpris-proxy so it bridges AVRCP <-> D-Bus
    proxy_proc = subprocess.Popen(
        ["/usr/bin/mpris-proxy"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("[MPRIS] mpris-proxy started (pid={})".format(proxy_proc.pid), flush=True)

    loop = GLib.MainLoop()
    loop.run()
