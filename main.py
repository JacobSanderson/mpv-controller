import logging
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
import threading
import subprocess
import tempfile
import socket
import os
import time
import shutil

logger = logging.getLogger(__name__)
MAX_ENTRIES = 8

CMDS = {
        "TRACK" : {
            "description" : "{playlist-name} | {time-pos-min}:{time-pos-sec}/{duration-min}:{duration-sec} ({percent-pos:.0f}%) | Track: {playlist-pos}-{playlist-count}",
            "action" : "cycle pause",
            "should-close" : False
            },
        "Next" : {
            "description" : "Go to the next track",
            "action" : "playlist-next",
            "should-close" : False
            },
        "Previous" : {
            "description" : "Go to the previous track",
            "action" : "playlist-prev",
            "should-close" : False
            },
        "Search" : {
            "description" : "Choose a dir to play in {working-directory}",
            "action" : "search",
            "should-close" : False
            },
        "Play/Pause" : {
            "description" : "Current Track: {current-track} (Idle: {idle})",
            "action" : "cycle pause",
            "should-close" : True
            },
        "Shuffle" : {
            "description" : "󰒟 current playlist",
            "action" : "playlist-shuffle",
            "should-close" : True
            },
        "Mute" : {
            "description" : "Un/mute current song (Mute: {mute})",
            "action" : "cycle mute",
            "should-close" : True
            },
        "Stop" : {
            "description" : "Close current mpv",
            "action" : "stop",
            "should-close" : True
            },
        "Volume up" : {
            "description" : "Add +5 to the volume:  {volume}%",
            "action" : "add volume 5",
            "should-close" : False
            },
        "Volume down" : {
            "description" : "Subtract 5 to the volume:  {volume}%",
            "action" : "add volume -5",
            "should-close" : False
            },
        "Fast Forward" : {
            "description" : "Skip 10s forward",
            "action" : "add time-pos 10",
            "should-close" : False
            },
        "Fast Backward" : {
            "description" : "Go back 10s",
            "action" : "add time-pos -5",
            "should-close" : False
            }
        }

def getpid(process:str = "mpv"):
    ROOT = "/proc"
    proc_dir = os.listdir(ROOT)
    for pid in proc_dir:
        path = os.path.join(ROOT, pid)
        if (not os.path.isdir(path)):
            continue
        status = os.path.join(path, "status")
        if not os.path.exists(status):
            continue
        name = open(status, "r").readline()[:-1].removeprefix("Name:\t")
        if name == process:
            file = open(status, "r").readlines()
            state = file[2][:-1].removeprefix("State:\t")
            print(state)
            return int(pid)
    return -1

def get_data(socket_path:str, properties:list | str) -> dict:
    if isinstance(properties, str):
        properties = [properties]
    res = {}
    if getpid("mpv") == -1:
        return res
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        for pr in properties:
            cmd = "{ \"command\": [\"get_property\", \"" + pr + "\"] }\n"
            client.send(cmd.encode())
            data = client.recv(2**16).decode()[:-1]
            try:
                data = data.replace("true", "True")
                data = data.replace("false", "False")
                res[pr] = eval(data)["data"]
            except Exception as e:
                res[pr] = None
    return res

def get_name(socket_path:str, relative_pos:int):
    try:
        index = list(get_data(socket_path, "playlist-pos").values())[0]
        thing = list(get_data(socket_path, f"playlist/{index+relative_pos}/filename").values())[0]
    except Exception as e:
        return ""
    if thing == None:
        return ""
    name = os.path.basename(thing)
    name = os.path.splitext(name)[0]
    return name

def get_fmt(socket_path:str, fmt:str):
    options = ["volume", "playlist-pos", "playlist-count",
            "time-pos", "time-remaining", "percent-pos", "duration", 
            "media-title", "filename/no-ext", "working-directory",
            "audio-speed-correction", "path", "idle", "mute"]
    try:
        subs = get_data(socket_path, options)
        subs["current-track"] = get_name(socket_path, 0)
        subs["next-track"] = get_name(socket_path, 1)
        subs["previous-track"] = get_name(socket_path, -1)
        subs["playlist-name"] = os.path.basename(os.path.dirname(subs["path"]))
        subs["time-pos-sec"]  = int(subs["time-pos"])%60
        subs["time-pos-min"]  = int(subs["time-pos"])//60
        subs["time-pos-hour"] = int(subs["time-pos"])//60//60
        subs["duration-sec"]  = int(subs["duration"])%60
        subs["duration-min"]  = int(subs["duration"])//60
        subs["duration-hour"] = int(subs["duration"])//60//60
        fmt  = fmt.format(**subs)
    except Exception as e:
        logger.error(e)
    return fmt

def search2(needle:str|None, haystack:list[str]):
    if needle == "" or needle == None:
        return haystack
    cmd = ["fzf", "-f", needle]
    if shutil.which("fzf") == None:
        cmd = ["grep", "-iF", needle]
        #  return haystack
    args = "\n".join(haystack)
    with tempfile.TemporaryFile() as stin:
        stin.write(args.encode())
        stin.seek(0)
        with tempfile.TemporaryFile() as stout:
            proc = subprocess.Popen(cmd, stdin=stin, stdout=stout)
            proc.wait(1.)
            if proc.returncode != 0:
                return []
            stout.seek(0)
            res = [line.decode()[:-1] for line in  stout.readlines()]
    return res

def getplaylists(music_dir:str, query:str):
    music_dir = os.path.expanduser(music_dir)
    dirs = os.listdir(music_dir)
    dirs = search2(query, dirs)
    items = []
    for name in dirs[:MAX_ENTRIES]:
        path = os.path.join(music_dir, name)
        if not os.path.isdir(path):
            continue
        ntracks = len(os.listdir(path))
        desc = f"{ntracks} tracks."
        action = "mpv-play " + path
        items.append(
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=name,
                    description=desc,
                    on_enter=ExtensionCustomAction(action),
                    on_alt_enter=ExtensionCustomAction(action)) 
                )
    return items
    
def control_mpv(socket_path:str, cmd:str):
    cmd = cmd + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.send(cmd.encode())
        return

def get_current_options(socket_path:str, music_dir:str, query:str):
    cmds = list(CMDS.keys())
    if getpid("mpv") == -1:
        cmds = ["Search"]
    logger.info(f"Current query: {query}")
    if query == None:
        pass
    elif query.startswith("search"):
        nquery = query.removeprefix("search")
        return getplaylists(music_dir, nquery)
    else:
        cmds = search2(query, cmds)
    items = []
    for key in cmds[:MAX_ENTRIES]:
        val = CMDS[key]
        # Format descriptions
        try:
            desc = get_fmt(socket_path, val["description"]) 
        except KeyError:
            desc = val["description"]
        action = val["action"]
        depends = not val["should-close"]
        # Format keys
        if key == "TRACK":
            key = get_fmt(socket_path, "{current-track}")
        elif key == "Next":
            key = get_fmt(socket_path, "󰒭 {next-track}")
        elif key == "Previous":
            key = get_fmt(socket_path, "󰒮 {previous-track}")

        action = ExtensionCustomAction(action, keep_app_open=depends)
        if key == "Search":
            action = SetUserQueryAction("m search ")
        # Fill stuff
        items.append(ExtensionResultItem(
            icon="images/icon.png",
            name=key, description=desc,
            on_enter=action, on_alt_enter=action))
    return items

#######################################
# Main Extension Classes
#######################################
class DemoExtension(Extension):
    def __init__(self):
        super(DemoExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, IntemEnterEventListener())
        self.last_query = ""

# What happens sometimes when i press enter
class IntemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        socket_path = extension.preferences["mpv-config"]
        socket_path = os.path.expanduser(socket_path)
        music_dir  = extension.preferences["music-directory"]
        music_dir  = os.path.expanduser(music_dir)
        args = event.get_data()
        cmd = args
        if cmd.startswith("mpv-play"):
            playlist = cmd.removeprefix("mpv-play ")
            func = lambda: subprocess.run(["mpv", "--no-audio-display", playlist])
            t = threading.Thread(target=func, daemon=False)
            t.start()
        elif cmd == "search":
            playlists = getplaylists(music_dir, "")
            return RenderResultListAction(playlists)
        else:
            t = threading.Thread(target=control_mpv, args=(socket_path, cmd), daemon=False)
            t.start()
        time.sleep(0.02) #wait for socket to update from data change before
        return RenderResultListAction(get_current_options(socket_path, music_dir, extension.last_query))


# What happens on keyword search
class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        socket_path = extension.preferences["mpv-config"]
        socket_path = os.path.expanduser(socket_path)
        music_dir  = extension.preferences["music-directory"]
        music_dir  = os.path.expanduser(music_dir)
        kw = event.get_keyword()
        query = event.get_argument()
        extension.last_query = query
        items = get_current_options(socket_path, music_dir, query)
        return RenderResultListAction(items)

if __name__ == "__main__":
    DemoExtension().run()
