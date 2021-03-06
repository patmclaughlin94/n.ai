import os
import time
import pprint
from slackclient import SlackClient

import api_ai
from nutrition_ai import nutrition_ai as na
from amazon_buyer import amazon_buyer as ab
from route_planner import route_planner as rp


#from environ variable
BOT_ID = os.environ.get("BOT_MANAGER_ID")
BOT_MANAGER_CHANNEL = os.environ.get("BOT_MANAGER_CHANNEL")

#constants
AT_BOT = "<@" + BOT_ID + ">"
BOT_SESSION_ID = "bot_manager"

service_dag = { 
                'start'                 : ['nutrition_ai'],
                'nutrition_ai'          : ['cart_online', 'cart_offline'],
                'cart_online'           : ['amazon_buyer'],
                'cart_offline'          : ['route_planner'],
                'amazon_buyer'          : ['end'],
                'route_planner'         : ['end'],
                'end'                   : ['start']
              }

next_message = {
                'nutrition_ai'          : 'What would like to buy online?',
                'cart_online'           : 'What you like to buy online?',
				'cart_offline'			: 'What would you like to buy in person?',
                'amazon_buyer'          : 'Let me find the items you want to buy online.',
                'route_planner'         : 'What is your starting address?',
                'end'                   : 'Have a safe trip!'
               } 


#instantiate Slack client
slack_client = SlackClient(os.environ.get('BOT_MANAGER_TOKEN'))

def handle_command(command, channel, cart_intent):
    """
        Receives commands directed at the bot and determines if they
        are valid commands. If so, then acts on the commands. If not,
        returns back what it needs for clarification.
    """
    response = "Can you please repeat what you said?"

    apiai_query = command
    print command
    apiai_resp = api_ai.query_apiai(apiai_query, BOT_SESSION_ID, cart_intent)
    pprint.pprint(apiai_resp)

    response = unicode(apiai_resp['result']['fulfillment']['speech'])
    slack_client.api_call("chat.postMessage", channel=channel,
                            text=response, as_user=True)
 
    if apiai_resp['result']['action'] == 'cart_offline':
        if apiai_resp['result']['actionIncomplete'] == False:
            items_offline = api_ai.parse_result(apiai_resp, cart_intent)	
            return items_offline

    if apiai_resp['result']['action'] == 'cart_online':
        if apiai_resp['result']['actionIncomplete'] == False:
            items_online = api_ai.parse_result(apiai_resp, cart_intent)	
            return items_online

#    slack_client.api_call("chat.postMessage", channel=channel,
#							text=response, as_user=True)


def parse_slack_output(slack_rtm_output):
    """
        The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.
    """
    output_list = slack_rtm_output
    if output_list and len(output_list) > 0:
        for output in output_list:
            if output and 'text' in output and AT_BOT in output['text']:
				#return text after the @mention, whitespace removed
                return output['text'].split(AT_BOT)[1].strip().lower(), \
                        output['channel']

    return None, None

if __name__ == "__main__":
    READ_WEBSOCKET_DELAY = 1
    if slack_client.rtm_connect():
        print "bot_manager connected and running!\n"

        service_queue = ['start']
        service_queue.extend(service_dag['start'])
        del service_queue[0]
        print service_queue

        food_city_place = None
        items_online = None
        items_offline = None
        city_places = list()

        while True:
            command, channel = parse_slack_output(slack_client.rtm_read())
            if command and channel:
                if channel == BOT_MANAGER_CHANNEL:

                    if service_queue[0] == "nutrition_ai":
                        food_city_place = na.handle_command(command, channel) 
                        pprint.pprint(food_city_place)
                        service_queue.extend(service_dag[service_queue[0]])
                        del service_queue[0]
                        slack_client.api_call('chat.postMessage', channel=channel, 
                                            text=next_message[service_queue[0]], as_user=True)
                        print service_queue

                    elif service_queue[0] == 'cart_online':
                        items_online = handle_command(command, channel, "online")
                        pprint.pprint(items_online)
                        service_queue.extend(service_dag[service_queue[0]])
                        del service_queue[0]
                        slack_client.api_call('chat.postMessage', channel=channel,
                                            text=next_message[service_queue[0]], as_user=True)
                        print service_queue

                    elif service_queue[0] == 'cart_offline':
                        items_offline = handle_command(command, channel, "offline")
                        pprint.pprint(items_offline)
                        service_queue.extend(service_dag[service_queue[0]])
                        del service_queue[0]

                        pprint.pprint(items_offline) 
                        pprint.pprint(food_city_place)

                        for item in items_offline:
                            for food, city_place in food_city_place.iteritems():
                                if item.title() == food:
                                    city_places.append(city_place)
                        
                        #pprint.pprint(city_places)
                        if not city_places:
                            distinct_city_places = list(set(food_city_place.values()))
                            city_places.append(distinct_city_places[-1])
                        pprint.pprint(city_places)

                        stores_msg_user = "You can get all the ingredients at these stores:\n"
                        for place in city_places:
                            stores_msg_user = stores_msg_user + "\t" + place + "\n"

                        slack_client.api_call('chat.postMessage', channel=channel,
                                            text=stores_msg_user, as_user=True)

                        items_offline = None
                        city_places = list()

                        slack_client.api_call('chat.postMessage', channel=channel,
                                            text=next_message[service_queue[0]], as_user=True)
                        print service_queue

                    #elif service_queue[0] == 'amazon_buyer':
                        print "in amazon_buy"
                        amazon_buy = "I want to get"
                        for i in range(len(items_online)):
                            if i == (len(items_online) - 1):
                                amazon_buy = amazon_buy + " and " + items_online[i]
                            elif i == 0:
                                amazon_buy = amazon_buy + " " + items_online[i]
                            else:
                                amazon_buy = amazon_buy + ", " + items_online[i]
                        ab.handle_command(amazon_buy, channel)
                        service_queue.extend(service_dag[service_queue[0]])
                        del service_queue[0]
                        slack_client.api_call('chat.postMessage', channel=channel,
                                            text=next_message[service_queue[0]], as_user=True)
                        items_online = None
                        print service_queue
                    
                    elif service_queue[0] == 'route_planner':
                        is_finished = rp.handle_command(command, channel)
                        if is_finished:
                            service_queue.extend(service_dag[service_queue[0]])
                            del service_queue[0]

                            slack_client.api_call('chat.postMessage', channel=channel,
                                            text=next_message[service_queue[0]], as_user=True)

                    else:
                        print "what's the service you're asking for?"
                    
                else:
                    print "got a message NOT from computer networks"

            if service_queue[0] == 'end':
                if len(service_queue) == 1:
                    service_queue.extend(service_dag[service_queue[0]])
                    print "Restarting the service"
                else:
                    print "Reached an end state"
                    del service_queue[0]
            if service_queue[0] == 'start':
                service_queue.extend(service_dag[service_queue[0]])
                del service_queue[0]

            print service_queue
            time.sleep(READ_WEBSOCKET_DELAY)
            print None
    else:
        print "Connection failed. Invalid Slack token or Bot ID?\n"
