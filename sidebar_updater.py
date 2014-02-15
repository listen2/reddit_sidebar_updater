#!/usr/bin/python3

import html.parser
import time
import socket
import urllib.request
from xml.dom.minidom import parseString
from threading import Thread
from string import Template
import configparser

import lightreddit

config = configparser.ConfigParser()
config.read("/srv/bots/sidebar_updater/sidebar_config.ini")

rules = []
for s in config.sections():
	r = {}
	for k in ["rname", "sentinel", "template", "user", "pass"]:
		r[k] = config.get(s, k)
	rules.append(r)

def time_to_dhms(ti):
	"""Takes time in unixtime; returns (days, hours, minutes, seconds)
	"""
	secs = int(ti - time.time())
	days = int(secs / 86400)
	#secs -= days * 86400
	hours = int(secs / 3600)
	#secs -= hours * 3600
	mins = int(secs / 60)
	return (days, hours, mins, secs)

def time_left(ti):
	(days, hours, mins, secs) = time_to_dhms(ti)
	if secs < 0:
		return "has launched!"
	elif mins < 60:
		return "launch in %s minutes" % (mins)
	elif hours < 24:
		return "launch in %s hours" % (hours)
	else:
		return "launch in %s days" % (days + 1)

class BNetChecker(Thread):
	"""
	Checks whether the D3 realms are up, and if not, gets the message.
	"""
	def trunc(self, msg, more):
		msg = msg.replace("\n\n", "—", 1)
		msg = msg.replace("\n\n", "\n")
		if len(msg) > 300:
			return "[%s...](/smallText) [Read more](%s)" % (msg[:301].rsplit(" ", 1)[0], more)
		return msg

	def run(self):
		self.am = "AM: "
		self.eu = "|EU: "
		self.asia = "|AS: "
		self.status = ""

		html = urllib.request.urlopen("http://us.battle.net/d3/en/status").read()

		_status_dom = parseString(html)

		regions = ["enus", "engb", "zhtw"]
		other_regions = {"am": {"pretty":"Americas", "url":"http://us.launcher.battle.net/service/d3/alert/en-us"},
				"eu": {"pretty":"Europe", "url":"http://eu.launcher.battle.net/service/d3/alert/en-gb"},
				"as": {"pretty":"Asia", "url":"http://sea.launcher.battle.net/service/d3/alert/en-us"}}
		bnet_build = {}
		client_build = {}

		global _db_dir_inner
		_db_dir_inner = None
		def find_html_class(n, cl):
			global _db_dir_inner
			try:
				if n._attrs["class"].value == "db-directory-inner":
					_db_dir_inner = n
					return
			except KeyError:
				pass
			except AttributeError:
				pass
			except TypeError:
				pass

			for e in n.childNodes:
				find_html_class(e, cl)
		find_html_class(_status_dom, "a")

		status_response = {}
		status_response["am"] = _db_dir_inner.childNodes[1].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		status_response["eu"] = _db_dir_inner.childNodes[3].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		status_response["as"] = _db_dir_inner.childNodes[5].childNodes[1].childNodes[3].childNodes[1].childNodes[1]._attrs["class"].nodeValue.split()[1]
		self.am = "AM: " + (("[online](/bnetOnline)") if status_response["am"] == "up" else "[Offline](/bnetOffline)")
		self.eu = "|EU: " + (("[online](/bnetOnline)") if status_response["eu"] == "up" else "[Offline](/bnetOffline)")
		self.asia = "|AS: " + (("[online](/bnetOnline)") if status_response["as"] == "up" else "[Offline](/bnetOffline)")

		for r in ["am", "eu", "as"]:
			if not status_response[r] == "up":
				resp, alertMessage = h.request(other_regions[r]["url"], "GET")
				if len(alertMessage) > 10:
					alertMessage = self.trunc(alertMessage.decode("utf8"), other_regions[r]["url"])
					self.status += "%s alert\n------------------\n\n%s\n\n" % (other_regions[r]["pretty"], alertMessage)
				return

class IRCChecker(Thread):
	"""
	Gets the number of users currently in IRC
	"""
	def run(self):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		except socket.OSError as e:
			print("Failed to create socket: %s" % (e))

		s.settimeout(5)

		try:
			remote_ip = socket.gethostbyname("tucana.whatbox.ca")
		except socket.gaierror:
			print("Hostname could not be resolved.")

		try:
			s.connect((remote_ip, 42666))
		except socket.timeout:
			print("Socket connection timed out.")
			self.irc_size = ""
			s.close()
			return

		try:
			s.sendall(b"irc_users\n")
		except socket.error:
			print("Send failed")

		try:
			self.irc_size = " (%s users)" % (s.recv(4096).decode("utf8"))
		except socket.timeout:
			self.irc_size = ""

		s.close()

		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		except socket.OSError as e:
			print("Failed to create socket: %s" % (e))

		s.settimeout(5)

		try:
			remote_ip = socket.gethostbyname("tucana.whatbox.ca")
		except socket.gaierror:
			print("Hostname could not be resolved.")

		try:
			s.connect((remote_ip, 42666))
		except socket.timeout:
			print("Socket connection timed out.")
			self.irc_size = ""
			s.close()
			return

		try:
			s.sendall(b"mumble_users\n")
		except socket.error:
			print("Send failed")

		try:
			self.mumble_size = " (%s users)" % (s.recv(4096).decode("utf8").split("\n", maxsplit=1)[0])
		except socket.timeout:
			self.mumble_size = ""

		s.close()

for g in rules:
	#create threads to handle slow (network-dependent) fetches
	threads = {}
	threads["bnet"] = BNetChecker()
	threads["irc"] = IRCChecker()

	for t in threads:
		threads[t].start()

	# Create lightreddit object
	r = lightreddit.RedditSession(g["user"], g["pass"], "/r/diablo sidebar updater. Contact /u/listen2")

	# Grab current settings
	subr_info = r.get_subreddit_settings(g["rname"])
	subr_desc = subr_info["description"][(subr_info["description"].find(g["sentinel"])+len(g["sentinel"])):]

	# There has to be a way to get rid of the HTMLParser
	HP = html.parser.HTMLParser()
	subr_desc = HP.unescape(subr_desc)

	# Calculate time until release.
	#secs = int(1337065200 - time.time())+3600 # 15 May 2012 00:00:00 PDT # Add 3600 because it truncates; this simulates a round up.
	end = 1395705600
	total_seconds = 9158400
	releaseDateCounter = "[Reaper of Souls %s](/releaseCountdown)\n\n" % time_left(end)
	percentage = int(((time.time() - 1387411200) / (total_seconds)) * 10)*10
	releaseDateCounter += "[%s%%](/%sp)[%s%%](/%sn)\n\n" % (percentage, percentage, 100-percentage, 100-percentage)

	#releaseDateCounter += "[Diablo 3 Europe " + time_left("eu") + "](/releaseCountdown)\n\n"
	#releaseDateCounter += "[Diablo 3 Asia " + time_left("sea") + "](/releaseCountdown)\n\n"

	with open("/tmp/rdiablo_thread_gear_tid", "r") as f:
		tid_gear = f.read().rstrip()

	with open("/tmp/rdiablo_thread_loot_tid", "r") as f:
		tid_loot = f.read().rstrip()

	with open("/tmp/rdiablo_thread_questions_tid", "r") as f:
		tid_questions = f.read().rstrip()

	with open("/tmp/rdiablo_thread_challenge_tid", "r") as f:
		tid_challenge = f.read().rstrip()

	lastUpdated = "[Last updated at " + time.strftime("%H:%M:%S UTC", time.gmtime()) + "](/smallText)"

	# Wait for threads to finish, if they haven't already
	for t in threads:
		threads[t].join()

	# Update subreddit description
	with open(g["template"], "r") as t:
		t = t.read().rstrip()
	newDescription = Template(t)

	newDescription = newDescription.substitute(
		release=releaseDateCounter,
		am=threads["bnet"].am,
		eu=threads["bnet"].eu,
		asia=threads["bnet"].asia,
		alert=threads["bnet"].status,
		irc_size=threads["irc"].irc_size,
		mumble_size=threads["irc"].mumble_size,
		lastUpdated=lastUpdated,
		gear=tid_gear,
		loot=tid_loot,
		questions=tid_questions,
		challenge=tid_challenge,
		sentinel=str(g["sentinel"]),
		subr_desc=subr_desc)
	r.wiki_write(g["rname"], "config/sidebar", newDescription)
	#print(newDescription)
