#!/usr/bin/python
from __future__ import with_statement
from IPython import embed
from fabric.api import *
from fabric.contrib.console import confirm
from fabric.colors import red, green, blue, yellow
import json
import os
import openstack.compute
import clouddns
import datetime

now = datetime.datetime.now()
datetime = now.strftime("%Y-%m-%d_%H:%M")

from cuisine import *

with open('./keys.json') as f:
	keychain = json.load(f)
	compute = openstack.compute.Compute(username=keychain['rackspaceuser'], apikey=keychain['rackspaceapikey'])
	dns = clouddns.connection.Connection(keychain['rackspaceuser'], keychain['rackspaceapikey'])

with open('./host-aliases.json') as f:
	hostaliases = json.load(f)
	for key,val in enumerate(env.hosts):
		env.hosts[key] = nicenametohost(val)

env.user = 'root'

vhostroot = '/var/www/vhost/'
apachevhostconfigdir = '/etc/apache2/sites-available'

def setup():
	group_ensure("remote_admin")
	user_ensure("admin")
	group_user_ensure("remote_admin", "admin")

def addtohosts(host):
	env.hosts.append(str(host))
	env.host_string = str(host)
	updatehosts()

def updatehosts():
	for key,val in enumerate(env.hosts):
		env.hosts[key] = nicenametohost(val)
		env.host_string = nicenametohost(val)

def dovhostcommand(vhost, command):
	location = vhostroot + vhost + 'public/'
	if "wwwpermissions" in command:
		wwwpermissions(location)

def newlampvhost(domain, dbname, installcms=False, ip=False, skipbackup=False):
	if not ip:
		ip = gethostipbyhost(env.host_string)
	if not skipbackup:
		serverimagemk(True)
	entry,parent = splitsubdomain(domain)
	dnsmk(parent,ip,entry)
	newapachevhost(domain)
	newmysqldb(dbname)
	newmysqluserpassword = createrandompassword()
	print "New user password: " + newmysqluserpassword
	newmysqluser(dbname, dbname, newmysqluserpassword)
	if installcms == "wordpress":
		installwordpress(stable, vhostroot + domain + 'public/')
		wwwpermissions(vhostroot + domain + 'public/')

def newapachevhost(url):
	with cd(apachevhostconfigdir):
		put('./apache-vhost-template.conf', url)
	#run('a2newsite ' + url)

def newmysqldb(dbname):
	run('sqlnewdb ' + dbname)

def newmysqluser(dbname, dbuser, dbpassword):
	run('sqlnewdbuser ' + dbname + ' ' + dbuser)

def installwordpress(version, location):
	version_commands = {
		'stable': 'svn co http://core.svn.wordpress.org/tags/3.5.2 .',
		'trunk':'svn co http://core.svn.wordpress.org/trunk/ .'
	}
	run('cd ' + location)
	run(version_commands[version])

def wwwpermissions(directory):
	run('cd ' + directory)
	run('chown www-data -R ./*')

@hosts('allstruck.org')
def dnsmk(domain, location=False, subdomain=False, recordtype='A'):
	print "Starting DNSMK task"
	print "Domain = " + domain
	print "Location = " + location
	print "Subdomain = " + subdomain
	if subdomain and subdomain != domain:
		print "Creating record in " + domain + " for " + subdomain + " at " +location + " type: " + recordtype
		parent = dns.get_domain(name=domain)
		parent.create_record(subdomain, location, recordtype)
	else:
		if dns.get_domain(name=domain):
			print "Creating main record in " + domain
			dns.create_record(subdomain, location, recordtype)
		else:
			print "Creating root domain " + domain
			dns.create_domain(name=domain, ttl=300, emailAddress=domain + '@allstruck.com')

def aptupdate():
	run('sudo apt-get update')

def aptupgrade():
	run('sudo apt-get upgrade')

# RackSpace Server and DNS Stuff:
@hosts('allstruck.org')
def dnsrm(domain, subdomain=False):
	try:
		domain = dns.get_domain(name=domain)
	except ValueError:
		print "That domain (" + domain + ") doesn't work!"
	if subdomain:
		try:
			record = domain.get_record(name=subdomain)
		except ValueError:
			print "That subdomain (" + subdomain + " doesn't work!"
		domain.delete_record(record.id)
	else:
		dns.delete_domain(domain.id)

@hosts('allstruck.org')
def dnsls(domain=False):
	if domain:
		domain = dns.get_domain(name=domain)
		for record in domain.get_records():
			print '(%s) %s -> %s' % (record.type, record.name, record.data)
	else:
		for domain in dns.get_domains():
			print domain.name

def serverimagemk(wait=False):
	server = compute.servers.find(name=getserverbyname(env.host_string))
	compute.images.create(getserverbyname(env.host_string) + '-' + datetime, server)
	image = compute.images.find(name=getserverbyname(env.host_string) + '-' + datetime)
	if wait:
		print "Waiting for server image to complete."
		serverimageprogresswatcher(image.id)

def serverimagels(imagename=False,imageid=False):
	if imagename or imageid:
		if imageid:
			image = compute.images.get(imageid)
			print str(image) + ' {imageid=' + str(image.id) + '} ' + serverimagestatus(image.status)
			if image.status == 'SAVING':
				print 'Progress: ' + str(image.progress) + '%'
			print 'Created: ' + str(image.created)
			print 'Updated: ' + str(image.updated)
		else:
			images = compute.images.list()
			for image in images:
				if imagename in image.name:
					print str(image) + ' {imageid=' + str(image.id) + '} ' + serverimagestatus(image.status)
					if image.status == 'SAVING':
						print 'Progress: ' + str(image.progress) + '%'
					print 'Created: ' + str(image.created)
					print 'Updated: ' + str(image.updated)
					print '---'
	else:
		images = compute.images.list()
		for image in images:
			print str(image) + ' {imageid=' + str(image.id) + '} ' + serverimagestatus(image.status)
			if image.status == 'SAVING':
				print str(image.progress) + '%'

def serverimagestatus(status):
	if status == 'ACTIVE':
		return green(status)
	elif status == 'QUEUED':
		return yellow(status)
	elif status == 'SAVING':
		return blue(status)
	else:
		return red(status)

def serverimageprogress(imageid=False, verbosity=1):
	if not imageid:
		print "ERROR: Must provide imageid=id"
		return -1
	if not server_image_complete(imageid, 0):
		image = compute.images.get(imageid)
		if hasattr(image, 'status'):
			if image.status == 'SAVING':
				if hasattr(image, 'progress'):
					if verbosity > 0:
						print 'Progress: ' + str(image.progress) + '%'
						return image.progress
				else:
					return 0
			elif image.status == 'QUEUED':
				if verbosity > 0:
					print 'Queued'
				return 0
			else:
				 if verbosity > 0:
				 	print '100% Complete'
		else:
			if verbosity > 0:
				print "There's not a status property on image :("
			return 0
	else:
		if verbosity > 0:
			print "100 % Complete"
		return 100

def server_image_complete(imageid=False, verbosity=1):
	if not imageid:
		print "ERROR: Must provide imageid=id"
		return
	image = compute.images.get(imageid)
	if image.status == 'SAVING':
		if verbosity > 0:
			print 'Not done.'
		return False
	elif image.status == 'ACTIVE':
		if verbosity > 0:
			print 'Complete!'
		return True
	elif image.status == 'QUEUED':
		if verbosity > 0:
			print 'You entered the Queue, this is going to suck...'
		return False
	else:
		print 'Problem! image.status is: ' + str(image.status)
		return

def serverimageprogresswatcher(imageid, delay=23, verbosity=0):
	import time
	if not imageid:
		print "ERROR: Must provide imageid=id"
		return
	while not server_image_complete(imageid, verbosity):
		print str(serverimageprogress(imageid, verbosity)) + '%'
		time.sleep(delay)


def serverls(instance=False):
	if instance:
		servers = compute.servers.findall(name=getserverbyname(instance))
		for server in servers:
			print 'Name: ' + server.name
	else:
		servers = compute.servers.list();
		for server in servers:
			print server
			details = compute.servers.get(server)
			print 'Status: ' + details.status
			if details.status == 'ACTIVE':
				print 'Addresses: ' + str(details.addresses)
			else:
				print 'Progress: ' + str(details.progress)
			print ''

def splitsubdomain(domain):
	entry = parent = domain
	if domain.count('.') > 1:
		entry = domain
		parent = domain[domain.rfind('.',0,domain.rfind('.'))+1:]
	return entry,parent

def gethostipbyhost(host):
	ipaddresses = {
		'allstruck.com': 		'198.101.193.150',
		'allstruck.net:42123':	'204.232.207.253',
		'allstruck.org:42123': 	'204.232.201.73',
		'50.56.239.226:42123':	'50.56.239.226'
	}
	return ipaddresses[host]

def getserverbyname(host):
	names = {
		'allstruck.com': 		'Archimedes',
		'allstruck.net:42123': 	'AllStruckClients',
		'allstruck.org:42123': 	'McKay',
		'50.56.239.226:42123':	'Cooper'
	}
	if host in names:
		if names[host]:
			return names[host]
		else:
			return names[names.index(host)]

def nicenametohost(nicename):
	if nicename in hostaliases:
		return hostaliases[nicename]

def createrandompassword(length=8):
	import string
	from random import sample, choice
	chars = string.letters + string.digits
	return ''.join(choice(chars) for _ in xrange(length))

def test(message):
	print message

def stest(message):
	run('echo ' + message)

def interactive():
	embed() # this call anywhere in your program will start IPython
