from linebot import  LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
from bs4 import BeautifulSoup
from urllib.parse import parse_qs
import requests
import json
import uuid
import boto3
import os
import re

s3 = boto3.client(
    's3', 
    aws_access_key_id=os.environ['aws_access_key_id'], 
    aws_secret_access_key=os.environ['aws_secret_access_key'], 
    region_name=os.environ['region_name']
)

class FaceFinder:
    def __init__(self, img) :
        self.s3_client = boto3.client(
            's3', 
            aws_access_key_id=os.environ['aws_access_key_id'], 
            aws_secret_access_key=os.environ['aws_secret_access_key'], 
            region_name=os.environ['region_name']
        )
        self.rek = boto3.client(
            'rekognition',
            aws_access_key_id=os.environ['aws_access_key_id'], 
            aws_secret_access_key=os.environ['aws_secret_access_key'], 
            region_name=os.environ['region_name']
        )
        self.img = img

    def index_from_collection(self, MaxFaces=3, FaceMatchThreshold=30):
        collection = []
        with open(self.img, 'rb') as f :
            response = self.rek.search_faces_by_image(
                CollectionId=os.environ['CollectionId'],
                Image={
                    'Bytes':f.read()
                },
                MaxFaces=MaxFaces,
                FaceMatchThreshold=FaceMatchThreshold
            )
            if response['ResponseMetadata']['HTTPStatusCode'] == 200 :
                for face in response['FaceMatches'] :
                    collection.append(
                        {
                            'ImgURL': 'https://%s.s3-ap-northeast-1.amazonaws.com/NSFW/%s.jpeg'%(os.environ['Bucket'], face['Face']['ExternalImageId']),
                            'Similarity': face['Similarity'],
                            'TagSet': self.s3_client.get_object_tagging(Bucket=os.environ['Bucket'],Key='NSFW/%s.jpeg'%face['Face']['ExternalImageId'])['TagSet']
                        }
                    )
        return collection
    
    def index_from_celebrities(self, threshold=30):
        collection = []
        with open(self.img, 'rb') as f :
            response = self.rek.recognize_celebrities(
                Image={
                    'Bytes':f.read()
                }
            )
        if response['ResponseMetadata']['HTTPStatusCode'] == 200 :
            print(response['CelebrityFaces'])
            for face in response['CelebrityFaces'] :
                # Get matched celebrity image.
                r = requests.get('https://' + face['Urls'][0])
                soup = BeautifulSoup(r.content, 'html.parser')
                ele = soup.find_all(id='name-poster')
                if ele :
                    ImgURL = ele[0]['src']
                    collection.append(
                        {
                            'ImgURL': ImgURL,
                            'Similarity': face['MatchConfidence'],
                            'TagSet': [{'Value' : face['Name']}]
                        }
                    )
        return collection

class FileIO :
    @classmethod
    def write_image_from_message(self, message_content) :
        with open('/tmp/user_upload.jpeg', 'wb') as f :
            for chunk in message_content.iter_content() :
                f.write(chunk)
        return '/tmp/user_upload.jpeg'
    @classmethod
    def write_token_json(self, token, result) :
        with open('/tmp/%s.json'%token, 'w') as f :
            json.dump(result, f)
        return '/tmp/%s.json'%token


def lambda_handler(even, context) :  
    for e in json.loads(even['body'])['events'] :
        if e['type'] == 'message' :
            if e['message']['type'] == 'image':
                # LINE authentication
                line_bot_api = LineBotApi(os.environ['channel_access_token'])
                handler = WebhookHandler(os.environ['channel_secret'])

                # extract image from message
                message_id = e['message']['id']
                message_content = line_bot_api.get_message_content(message_id)
                image_path = FileIO.write_image_from_message(message_content)

                # image processing
                FF = FaceFinder(image_path)
                other = FF.index_from_collection()
                celebrity = FF.index_from_celebrities()
                print(other, celebrity)

                # generate token and write static to s3
                token = uuid.uuid4().hex
                line_bot_api.reply_message(e['replyToken'], generateOption(token))

                file_path = FileIO.write_token_json(token, {
                    'other': other,
                    'celebrity': celebrity
                })
                FF.s3_client.upload_file(
                    Filename=file_path,
                    Bucket=os.environ['Bucket'],
                    Key='to-push/' + token + '.json',
                    ExtraArgs={'ACL': 'public-read'}
                )

        elif e['type'] == 'postback' :
            # LINE authentication
            line_bot_api = LineBotApi(os.environ['channel_access_token'])
            handler = WebhookHandler(os.environ['channel_secret'])
            params = {k : v for k, v in parse_qs(e['postback']['data']).items()}
            if params :
                data = requests.get('https://%s.s3-ap-northeast-1.amazonaws.com/to-push/%s.json'%(os.environ['Bucket'], params['token'][0])).json()
                result = data[params['type'][0]]
                if result :
                    contents = FlexSendMessage(alt_text='result', contents=generateReply(result))
                else :
                    contents = TextSendMessage(text='Sorry, No similar face has been found in %s'%params['type'][0])
                line_bot_api.reply_message(e['replyToken'], contents)

def generateOption(token) :
    return TemplateSendMessage(
        alt_text="Select your checking reference.",
        template=ConfirmTemplate(
            text="Select your checking reference.",
            actions=[
                PostbackAction(
                    label="Celebrities",
                    data="token=%s&type=celebrity"%token,
                    text="Celebrities"
                ),
                PostbackAction(
                    label="Other",
                    data="token=%s&type=other"%token,
                    text="Other"
                )
            ]
        )
    )
            
def generateReply(faces) :
    carousel = {
        "type": "carousel",
        "contents": []
    }
    for face in faces :
        carousel['contents'].append(
            {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                    {
                        "type": "image",
                        "url": "%s"%face["ImgURL"],
                        "size": "full",
                        "aspectMode": "cover",
                        "aspectRatio": "1:1",
                        "gravity": "center"
                    },
                    {
                        "type": "image",
                        "url": "https://scdn.line-apps.com/n/channel_devcenter/img/flexsnapshot/clip/clip15.png",
                        "position": "absolute",
                        "aspectMode": "fit",
                        "aspectRatio": "1:1",
                        "offsetTop": "0px",
                        "offsetBottom": "0px",
                        "offsetStart": "0px",
                        "offsetEnd": "0px",
                        "size": "full"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": x['Value'],
                                        "size": "md",
                                        "color": "#ffffff"
                                    } for x in face["TagSet"]
                                ]
                            },
                            {
                                "type": "text",
                                "text": "{}%".format(int(face['Similarity'])),
                                "color": "#ffffff",
                                "align": "start",
                                "size": "xs",
                                "gravity": "center",
                                "margin": "lg"
                              },
                              {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                  {
                                    "type": "box",
                                    "layout": "vertical",
                                    "contents": [
                                      {
                                        "type": "filler"
                                      }
                                    ],
                                    "width": "{}%".format(int(face['Similarity'])),
                                    "backgroundColor": "#808080",
                                    "height": "6px"
                                  }
                                ],
                                "backgroundColor": "#DCDCDC",
                                "height": "6px",
                                "margin": "sm"
                              }
                            ],
                            "spacing": "xs"
                        }
                        ],
                        "position": "absolute",
                        "offsetBottom": "0px",
                        "offsetStart": "0px",
                        "offsetEnd": "0px",
                        "paddingAll": "20px"
                    }
                    ],
                    "paddingAll": "0px"
                }
            }
        )
    return carousel
                