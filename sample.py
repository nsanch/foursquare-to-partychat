#!/usr/bin/python

import cgi
import logging
import urllib
import urllib2

from django.utils import simplejson

from google.appengine.api import users
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
            
# prod
config = {'server':'https://foursquare.com',
          'api_server':'https://api.foursquare.com',
          'redirect_uri': 'http://pchat-4sq-push.appspot.com/oauth',
          'client_id': '5VR53HSVGTI4MQUZWZDX4T5SCUHJP1BESLH2SNOAUFDZ1SZP',
          'client_secret': 'HG3GBHES5ORHFOZP52B0TLZSHF53PPRSU112OZL4OG4E3PKJ'}

class UserToken(db.Model):
  user = db.UserProperty()
  fs_id = db.StringProperty()
  token = db.StringProperty()
  twitter = db.StringProperty()

def fetchJson(url):
  logging.info('fetching url: ' + url)
  result = urllib2.urlopen(url).read()
  logging.info('got back: ' + result)
  return simplejson.loads(result)

def utf8(value):
  if isinstance(value, unicode):
    return value.encode("utf-8")
  assert isinstance(value, str)
  return value

class OAuth(webapp.RequestHandler):
  def post(self):
    self.get()

  def get(self):
    code = self.request.get('code')
    args = dict(config)
    args['code'] = code
    url = ('%(server)s/oauth2/access_token?client_id=%(client_id)s&client_secret=%(client_secret)s&grant_type=authorization_code&redirect_uri=%(redirect_uri)s&code=%(code)s' % args)
  
    json = fetchJson(url)

    token = UserToken()
    token.token = json['access_token']
    token.user = users.get_current_user()

    self_response = fetchJson('%s/v2/users/self?oauth_token=%s' % (config['api_server'], token.token))

    user_json = self_response['response']['user']
    token.fs_id = user_json['id']
    if user_json['contact'].get('twitter'):
      token.twitter = user_json['contact']['twitter']
    token.put()

    self.redirect("/")

def postToPartychat(message):
  url = 'http://partychat-hooks.appspot.com/post/p_mgfhm2u3'
  logging.info('posting to %s with %s' % (url, message))
  urllib2.urlopen(url, "message=%s" % urllib.quote_plus(utf8(message))).read()

def shouldSend(venue):
  return venue['id'] != '4ab7e57cf964a5205f7b20e3'

class ReceiveCheckin(webapp.RequestHandler):
  def post(self):
    logging.info('input = ' + self.request.body)

    json = simplejson.loads(self.request.body)
    checkin_json = json['checkin']
    user_json = json['user']

    token = UserToken.all().filter('fs_id =',user_json['id']).get()
    logging.info(token)
    if token and not token.twitter:
      self_response = fetchJson('%s/v2/users/self?oauth_token=%s' % (config['api_server'], token.token))
      user_json = self_response['response']['user']
      if user_json['contact'].get('twitter'):
        token.twitter = user_json['contact']['twitter']
        token.put()

    if token and token.twitter:
      userpath = token.twitter
    else:
      userpath = 'user/%s' % user_json['id']

    checkin_url = 'http://foursquare.com/%s/checkin/%s' % (userpath, checkin_json['id'])
    if checkin_json['type'] == 'shout':
      message = u'%s: %s shouted %s' % (checkin_url, user_json['firstName'], checkin_json['shout'])
    elif checkin_json.get('shout'):
      message = u'%s: %s checked in at %s: %s' % (checkin_url, user_json['firstName'],
                                             checkin_json['venue']['name'],
                                             checkin_json['shout'])
    else:
      message = u'%s: %s checked in at %s.' % (checkin_url, user_json['firstName'],
                                         checkin_json['venue']['name'])
    if (not checkin_json.get('venue')) or shouldSend(checkin_json['venue']):
      logging.info("posting %s" % message)
      postToPartychat(message)
    else:
      logging.info("not posting checkin")


class GetConfig(webapp.RequestHandler):
  def get(self):
    uri = '%(server)s/oauth2/authenticate?client_id=%(client_id)s&response_type=code&redirect_uri=%(redirect_uri)s' % config
    self.response.out.write(simplejson.dumps({'auth_uri': uri}))

application = webapp.WSGIApplication([('/oauth', OAuth), 
                                      ('/config', GetConfig),
                                      ('/checkin', ReceiveCheckin)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
