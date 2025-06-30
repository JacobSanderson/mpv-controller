import logging
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
import threading
import subprocess
import tempfile
import socket
import os

logger = logging.getLogger(__name__)
MUSIC_DIR = "/media/viktor/SSD-Verde/Multimedia/Musica"
SOCKET_DIR = os.path.expanduser("~/.config/mpv/socket")
#  tempfile = "ulauncher_mpvcontroller_tempfile"
MAX_ENTRIES = 8
WIDTH = 42

CMDS = {
        "search" : {
            "description" : "Search locally for music to play (NOT IMPLEMENTED)",
            "action" : "search"
            },
        "play/pause" : {
            "description" : "Play or pause current song",
            "action" : "cycle pause"
            },
        "next" : {
            "description" : "Go to next song in playlist",
            "action" : "playlist-next"
            },
        "previous" : {
            "description" : "Go to prev song in playlist",
            "action" : "playlist-prev"
            },
        "shuffle" : {
            "description" : "shuffle current playlist",
            "action" : "playlist-shuffle"
            },
        "mute/unmute" : {
            "description" : "un/mute current song",
            "action" : "cycle mute"
            },
        "stop" : {
            "description" : "stop all playlist",
            "action" : "stop"
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

def control_mpv(cmd:str):
    cmd = cmd + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(SOCKET_DIR)
        client.send(cmd.encode())
        return

def search2(needle:str, haystack:list[str]):
    if needle == "":
        haystack.sort()
        return haystack
    args = "\n".join(haystack)
    cmd = ["fzf", "-f", needle]
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

#######################################
# Main Extension Classes
#######################################
class DemoExtension(Extension):
    def __init__(self):
        super(DemoExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, IntemEnterEventListener())

# What happens sometimes when i press enter
class IntemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        args = event.get_data()
        cmd = args
        if cmd == "search":
            # TODO: implement this stuff
            return 
        else:
            t = threading.Thread(target=control_mpv, args=(cmd,), daemon=False)
            t.start()

# What happens on keyword search
class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        kw = event.get_keyword()
        query = event.get_argument()
        
        cmds = list(CMDS.keys())
        if query != "":
            cmds = search2(query, cmds)
        items = []
        for key in cmds[:MAX_ENTRIES]:
            val = CMDS[key]
            desc = val["description"]
            action = val["action"]
            items.append(ExtensionResultItem(
                icon="images/icon.png",
                name=key,
                description=desc,
                on_enter=ExtensionCustomAction(action),
                on_alt_enter=ExtensionCustomAction(action),
                ))

        return RenderResultListAction(items)


if __name__ == "__main__":
    DemoExtension().run()
