import html.parser
import time
#import socket
import httplib2
from xml.dom.minidom import parseString
from threading import Thread
from string import Template

sentinel = '[~s~](/s)'
subr_name = 'diablo'

#TODO this will be unnecessary after we set $PYTHONPATH
import sys
if "/srv/bots/common/praw" not in sys.path:
	sys.path.insert(0, "/srv/bots/common/praw")
import praw

class BNetChecker(Thread):
	"""
	Checks whether the D3 beta realm is up, and if not, gets the message.
	"""
	def trunc(self, msg, more):
		msg = msg.replace("\n\n", "—", 1)
		msg = msg.replace("\n\n", "\n")
		if len(msg) > 300:
			return "[%s...](/smallText) [Read more](%s)" % (msg[:301].rsplit(' ', 1)[0], more)
		return msg

	def run(self):
		h = httplib2.Http(".cache")
		resp, html = h.request("http://us.battle.net/d3/en/status", "GET")
		_status_dom = parseString(html)

		#resp, html = h.request("http://us.launcher.battle.net/d3/en-us/patch?patchVersion=0", "GET")
		#patch_dom = parseString(html)
		#client_ver_string = _patch_dom.childNodes[0].childNodes[3].childNodes[3].childNodes[3].childNodes[3].childNodes[1].childNodes[3].childNodes[1].childNodes[1].childNodes[0].childNodes[0].nodeValue.rsplit(" –", 1)[0].rsplit(" ", 1)[1]

		regions = ["enus", "engb", "zhtw"]
		other_regions = {"am": {"pretty":"Americas", "url":"http://us.launcher.battle.net/service/d3/alert/en-us"},
				"eu": {"pretty":"Europe", "url":"http://eu.launcher.battle.net/service/d3/alert/en-gb"},
				"as": {"pretty":"Asia", "url":"http://sea.launcher.battle.net/service/d3/alert/en-us"}}
		bnet_build = {}
		client_build = {}
		for r in regions:
			resp, html = h.request("http://"+r+".patch.battle.net:1119/patch", "POST", "<version program='D3'><record program='Bnet' component='Win' version='1' /><record program='D3' component='enUS' version='1' /></version>")
			_ver_dom = parseString(html)
			bnet_build[r] = _ver_dom.childNodes[0].childNodes[1].childNodes[0].nodeValue.rstrip().rsplit(";", 1)[1]
			client_build[r] = _ver_dom.childNodes[0].childNodes[3].childNodes[0].nodeValue.rstrip().rsplit(";", 1)[1]

		b = _status_dom.childNodes[0].childNodes[3].childNodes[0].childNodes[3].childNodes[1].childNodes[1].childNodes[3].childNodes[1].childNodes[1]
		status_response = {}
		status_response["am"] = b.childNodes[1].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		status_response["eu"] = b.childNodes[3].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		status_response["as"] = b.childNodes[5].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		#self.status = 'Diablo III game server status (v. ' + client_ver_string + ')'
		self.am = 'AM: ' + ('[online](/bnetOnline "' + bnet_build['enus'] + ', ' + client_build['enus'] + '")') if status_response["am"] == 'up' else '[Offline](/bnetOffline)'
		self.eu = '|EU: ' + (('[online](/bnetOnline "' + bnet_build['engb'] + ', ' + client_build['engb'] + '")') if status_response["eu"] == 'up' else '[Offline](/bnetOffline)')
		self.asia = '|AS: ' + (('[online](/bnetOnline "' + bnet_build['zhtw'] + ', ' + client_build['zhtw'] + '")') if status_response["as"] == 'up' else '[Offline](/bnetOffline)')

		self.status = ""
		for r in ["am", "eu", "as"]:
			if not status_response[r] == 'up':
				resp, alertMessage = h.request(other_regions[r]["url"], "GET")
				if len(alertMessage) > 10:
					alertMessage = self.trunc(alertMessage.decode("utf8"), other_regions[r]["url"])
					self.status += "%s alert\n------------------\n\n%s\n\n" % (other_regions[r]["pretty"], alertMessage)
				return

'''
class SlashdiabloChecker(Thread):
	"""
	Gets the number of users and games from slashdiablo
	"""
	def run(self):
		self.info = "[Slashdiablo](/r/slashdiablo) (server info unavailable)\n\n---\n\n"
		h = httplib2.Http(".cache")
		resp, html = h.request("http://ewalk0871.no-ip.org:8080/server.dat", "GET", headers={'Range': 'bytes=0-150'})

		d = html.decode("utf8").split("\n")
		self.info = "[Slashdiablo](/r/slashdiablo): %s players in %s games\n\n---\n\n" % (d[5][9:], d[4][6:])
'''

class MumbleChecker(Thread):
	"""
	Gets the number of users currently in mumble
	"""
	def run(self):
		h = httplib2.Http(".cache")
		resp, j = h.request("http://clanforge.multiplay.co.uk/public/servers.pl?event=Online;opt=ServerXml;serverid=140233", "GET")

		_mumble_dom = parseString(j)
		self.num_users = _mumble_dom.getElementsByTagName("numplayers")[0].firstChild.data
		self.max_users = _mumble_dom.getElementsByTagName("maxplayers")[0].firstChild.data

#create threads to handle slow (network-dependent) fetches
threads = {}
threads['bnet'] = BNetChecker()
#threads['slashdiablo'] = SlashdiabloChecker()
threads['mumble'] = MumbleChecker()

for t in threads:
	threads[t].start()

# Create reddit object and login
r = praw.Reddit(user_agent='/r/diablo sidebar updater [mellort python module]')
with open('/home/listen2/gharbad_pass', 'r') as f:
	p = f.read().rstrip()
r.login('GharbadTheWeak', p)
subreddit = r.get_subreddit(subr_name)

# Grab current settings
subr_info = subreddit.get_settings() # this broke for some reason
subr_desc = subr_info['description'][(subr_info['description'].find(sentinel)+len(sentinel)):]

# There has to be a way to get rid of the HTMLParser ;__;
HP = html.parser.HTMLParser()
subr_desc = HP.unescape(subr_desc)

with open('/tmp/irc_diablo_size', 'r') as f:
	irc_size = f.read()

lastUpdated = "[Last updated at " + time.strftime('%H:%M:%S UTC', time.gmtime()) + '](/smallText)'

# Wait for threads to finish, if they haven't already
for t in threads:
	threads[t].join()

# Update subreddit description
newDescription = Template("""Diablo III game server status

${am}${eu}${asia}
:--|:--|:--

$alert

---


$lastUpdated

----


[Heaven](http://dd.reddit.com/r/Diablo)[Select a theme](/#themeselector)[Hell](http://www.reddit.com/r/Diablo)

----

[@redditdiablo (Twitter)](http://www.twitter.com/redditdiablo) [/r/Diablo YouTube Channel](http://www.youtube.com/redditdiablo) [/r/Diablo@twitch.tv](http://www.justin.tv/rdiablo) [Steam Group](http://steamcommunity.com/groups/rdiablo)


**Community Links**

* [/r/Diablo browser extension](/10f7ce)

* [IRC channel](http://chat.mibbit.com/?url=irc://irc.esper.net/diablo) ($irc_size users)

    irc.esper.net #diablo

* [Mumble](http://tinyurl.com/7ulkl6l) ($mumble_users/$mumble_max users)

* [Slashdiablo](/r/slashdiablo) (server info unavailable)

* [How to get Battletag flair](/qyfqt)

$sentinel$subr_desc""")
newDescription = newDescription.substitute(
	am=threads['bnet'].am,
	eu=threads['bnet'].eu,
	asia=threads['bnet'].asia,
	alert=threads['bnet'].status,
	mumble_users=threads['mumble'].num_users,
	mumble_max=threads['mumble'].max_users,
	irc_size=irc_size,
	lastUpdated=lastUpdated,
	sentinel=str(sentinel),
	subr_desc=subr_desc)
subreddit.update_settings(description=newDescription)
#print(newDescription)
