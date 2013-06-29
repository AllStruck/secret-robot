#!/usr/bin/python
from __future__ import with_statement
from IPython import embed
from fabric.api import *
from fabric.contrib import files
from fabric.contrib.console import confirm
from fabric.colors import red, green, blue, yellow
import json
import sys, os
import openstack.compute
import clouddns
import datetime
import socket
from jinja2 import Environment, PackageLoader

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
		env.hosts[key] = hostaliases[val]

env.user = 'root'

vhostroot = '/var/www/vhost/'
apachevhostconfigdir = '/etc/apache2/sites-available/'

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

##MAIN##
def lampvhostmk(domain, dbname, installcms=False, ip=False, skipbackup=False):
	if not ip:
		ip = gethostipbyhost(env.host_string)
	if not skipbackup:
		serverimagemk(True)
	entry,parent = split_subdomain(domain)
	dnsmk(parent,ip,entry)
	apachevhostmk(domain)
	newmysqldb(dbname)
	newmysqluserpassword = createrandompassword()
	print "New user password: " + newmysqluserpassword
	newmysqluser(dbname, dbname, newmysqluserpassword)
	if installcms == "wordpress":
		installwordpress(stable, vhostroot + domain + 'public/')
		wwwpermissions(vhostroot + domain + 'public/')

# APACHE:
def apachevhostmk(url,skipenable=False):
	with cd(vhostroot):
		run('mkdir ' + url)
		with cd('./' + url):
			run('mkdir public log backup')
	with cd(apachevhostconfigdir):
		replacements = {
			'vhost_public_dir': vhostroot + url,
			'admin_email': getadminemail(url),
			'domain': url,
			'datetime':datetime + ' MST -0700'
		}
		print 'Uploading template...'
		files.upload_template(filename=os.getcwd()+"/apache-vhost-template.conf", destination=apachevhostconfigdir+url, context=replacements)
		if not skipenable:
			a2('ensite', url)
			a2('reload')
def apachevhostrm(url, safe=True):
	with settings(warn_only=True):
		a2('dissite', url)
		a2('reload')
		rm(vhostroot + url, '-rf', safe=safe)
		rm(apachevhostconfigdir + url, safe=safe)

# MYSQL:
def newmysqldb(dbname):
	run('sqlnewdb ' + dbname)

def newmysqluser(dbname, dbuser, dbpassword=False):
	run('sqlnewdbuser ' + dbname + ' ' + dbuser)


##
def getadminemail(subject='admin'):
	return subject + '@' + str(getdomainfromhost(env.host_string))

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
		server_image_progress_watcher(image.id)

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
	if not server_image_is_complete(imageid, 0):
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

def server_image_is_complete(imageid=False, verbosity=1):
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

def server_image_progress_watcher(imageid, delay=23, verbosity=0):
	import time
	if not imageid:
		print "ERROR: Must provide imageid=id"
		return
	while not server_image_is_complete(imageid, verbosity):
		print str(serverimageprogress(imageid, verbosity)) + '%'
		time.sleep(delay)


def cloudserverls(instance=False):
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

def split_subdomain(domain):
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

def getdomainfromhost(host):
	domains = {
		'allstruck.com': 		'allstruck.com',
		'allstruck.net:42123': 	'allstruck.com',
		'allstruck.org:42123': 	'allstruck.com',
		'50.56.239.226':	'allstruck.com'
	}
	return domains[host]

def a2(task='',att=''):
	tasks = {
		'restart': "run('/etc/init.d/apache2 restart')",
		'reload': "run('/etc/init.d/apache2 reload')",
		'ensite': "run('a2ensite ' + att)",
		'dissite': "run('a2dissite ' + att)",
		'enmod': "run('a2enmod ' + att)",
		'dismod': "run('a2dismod ' + att)",
		'sites-available': "run('ls " + apachevhostconfigdir + "')",
		'sites': "run('ls " + vhostroot + "')"
	}
	eval(tasks[task])

def nicenametohost(nicename):
	if nicename in hostaliases:
		return hostaliases[nicename]
	return nicename

def createrandompassword(length=8):
	import string
	from random import sample, choice
	chars = string.letters + string.digits
	return ''.join(choice(chars) for _ in xrange(length))

def ls(search='~/', att='-la'):
	run('ls --color ' + att + ' ' + search)
def rm(path, att='', safe=True):
	if safe:
		with shell_env(OS_USERNAME=keychain['rackspaceuser'], OS_API_KEY=keychain['rackspaceapikey'], OS_PASSWORD=keychain['rackspaceapikey'], OS_AUTH_URL='https://identity.api.rackspacecloud.com/v2.0/', OS_REGION_NAME='dfw'):
			if path[-4:] == '.zip':
				run('turbolift -r dfw upload --source '+path+' --container secret-robot-safe-delete')
			else: 
				# Zip contents of file or directory (and remove contents),
				#  upload to cloud files, then delete zip file:
				tempzipfilename = path+'-'+datetime+'.zip'
				run('zip -rTm '+tempzipfilename+' '+path)
				cloudfilesupload(tempzipfilename, 'secret-robot-safe-delete')
				run('rm ' + tempzipfilename)
	run('rm ' + att + ' ' + path)
def touch(path):
	run('touch ' + path)
def mkdir(dir):
	run('mkdir ' + dir)

def cloudfilesupload(source,container):
	run('turbolift -r dfw upload --source ' + source + ' --container ' + container)

def lprint(message):
	print message

def echo(message):
	run('echo ' + message)

def console():
	embed() # IPython

def c():
	console()