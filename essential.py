import time, os, sys
import re
import json
import cv2 as cv
import requests
# import numpy as np
# import random
import threading
import queue
import socket
import math
# from tkinter import *

dev_ip = "192.168.1.209"
rtsp_port = 554
http_port = 80

RECORD = False
SHOW   = True

screen_width = 640
screen_height= 360
frame_width  = 0
frame_height = 0
fps = 0
Running = True

def getVCAdata(url, q):
    global Running, frame_width, frame_height
    while Running :
        print ("starting vca")
        message_str = ''
        response = requests.get(url, stream=True) 
        print("starting vca",response, response.status_code)
        for content in response.iter_content(chunk_size=1):
            if not Running:
                return 0

            if content == b'@':
                if not message_str:
                    print ('@')
                    continue
                vca_data = json.loads(message_str)
                message_str = ''
                if not q.empty():
                # if q.qsize() >2:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                q.put((vca_data['timestamp'], vca_data))
                
            else:
                message_str += str(content, "utf-8") 
        
        print("exit vca", response, response.status_code, message_str)
        time.sleep(1)
    
    return 0


# def plot_one_box(pos, img, color=None, label=None, line_thickness=None):
#     # Plots one bounding box on image img
#     tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness
#     color = color or [random.randint(0, 255) for _ in range(3)]
#     c1, c2 = (int(pos[0]), int(pos[1])), (int(pos[2]), int(pos[3]))
#     cv.rectangle(img, c1, c2, color, thickness=tl, lineType=cv.LINE_AA)
#     if label:
#         tf = max(tl - 1, 1)  # font thickness
#         t_size = cv.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
#         c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
#         cv.rectangle(img, c1, c2, color, -1, cv.LINE_AA)  # filled
#         cv.putText(img, label, (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv.LINE_AA)

def plot_bbox(vca_data, img, img_size, line_thickness=None):
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness
    tf = max(tl - 1, 1)  # font thickness
    for data in vca_data['data'] :
        # color = [random.randint(0, 255) for _ in range(3)]
        color = (0,0,255)
        c1 = (int(img_size[0] * data['pos_lt'][0] // 0xFFFF), int(img_size[1] * data['pos_lt'][1] // 0xFFFF))
        c2 = (int(img_size[0] * data['pos_rb'][0] // 0xFFFF), int(img_size[1] * data['pos_rb'][1] // 0xFFFF))
        cv.rectangle(img, c1, c2, color, thickness=tl, lineType=cv.LINE_AA)
        if data['cat_item']:
            tf = max(tl - 1, 1)  # font thickness
            t_size = cv.getTextSize(data['cat_item'], 0, fontScale=tl / 3, thickness=tf)[0]
            c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
            cv.rectangle(img, c1, c2, color, -1, cv.LINE_AA)  # filled
            cv.putText(img, data['cat_item'], (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv.LINE_AA)
        
    cv.putText(img, vca_data['datetime'], (10, 40), 0, tl / 3, (225, 0, 0), thickness=tf, lineType=cv.LINE_AA)
        


def grabVideo(url, q):
    global Running, frame_width, frame_height,fps

    cap = cv.VideoCapture(url)
    ts = time.time()
    if cap.isOpened():
        ret, frame = cap.read()
        while not ret:
            ret, frame = cap.read()
    else :
        cap.release()
        return False

    frame_width  = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv.CAP_PROP_FPS))
    print(fps)

    while Running:
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = ts + int(cap.get(cv.CAP_PROP_POS_MSEC))/1000
        # if not q.empty():
        #     try:
        #         q.get_nowait()
        #     except queue.Empty:
        #         pass

        q.put((timestamp,frame))

    cap.release()

def showVideoVCA(q_frame, q_vca):
    global Running, frame_width, frame_height,fps
    vlength = 0
    recfps = 5.0

    while not frame_width:
        time.sleep(1)

    if RECORD:    
        fflag = 0
        tflag = 0

        fourcc = cv.VideoWriter_fourcc(*'XVID')
        fname_prefix = os.path.dirname(sys.argv[0]) + "/stream"
        fname = fname_prefix +"0.avi"
        video = cv.VideoWriter(fname, fourcc, recfps, (frame_width, frame_height))
    
    cv.namedWindow(dev_ip, cv.WINDOW_NORMAL)
    cv.resizeWindow(dev_ip, screen_width, screen_height)
    
    ts_vca = 0
    ts_frame = 2
    vca_data = {'frame_cnt': 0, 'timestamp': 0, 'datetime': '', 'object_count': 0, 'data': []}
    ddelay = 1/fps
    while Running:
        tss = time.time()
        if not q_frame.empty():
            (ts_frame, frame) = q_frame.get()
        if not q_vca.empty():
            # if ts_frame - ts_vca >2:
            (ts_vca, vca_data) = q_vca.get()

        

        plot_bbox(vca_data, frame, (frame_width, frame_height), line_thickness=None)
        tl = round(0.002 * (frame.shape[0] + frame.shape[1]) / 2) + 1  # line/font thickness
        tf = max(tl - 1, 1)  # font thickness

        cv.putText(frame, "%.2f, %.3f, %.3f, %.3f" %(fps, ts_frame, ts_vca, (ts_frame - ts_vca)), (10, 100), 0, tl / 3, (225, 0, 0), thickness=tf, lineType=cv.LINE_AA)

        if SHOW:
            cv.imshow(dev_ip, frame)

        if RECORD:
            video.write(frame)
        #     if vlength > 1200: # 30fps/3 => 10frame:1sec, 100frame => 10sec, 600frames => 1 minute
        #         video.release()
        #         fname = fname_prefix + str(fflag) + ".avi"
        #         fflag += 1
        #         vlength = 0
        #         video = cv.VideoWriter(fname, fourcc, recfps, (frame_width, frame_height))

        #     if tflag %3 == 0:
        #         video.write(frame)

        #     tflag = (tflag + 1)%3
        #     vlength += 1

        # print ("%.3f, %.3f, %d" %(ts_frame, ts_vca, vlength) )
        ch = cv.waitKey(1) &0xFF
        if ch == 27 or ch == ord('q') or ch == ord('Q'):
            Running = False
            break
        
        # print (1/fps)
        # time.sleep(0.033)
        ddelay = 1/fps -time.time() + tss - 0.01
        if ddelay > 0 :
            time.sleep(ddelay)
    
    
    Running = False
    for i in range(30):
        if not q_vca.empty():
            q_vca.get()    

    if RECORD:
        video.release()    
    cv.destroyAllWindows()

def showVideo(url, q):
    print ("starting video")
    global Running
    

    cap = cv.VideoCapture(url)

    if cap.isOpened():
        ret, frame = cap.read()
        while not ret:
            ret, frame = cap.read()
    else :
        cap.release()
        sys.exit()

    frame_width  = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    timestamp   = int(cap.get(cv.CAP_PROP_POS_MSEC))/1000
    print(timestamp)

    if RECORD:    
        fourcc = cv.VideoWriter_fourcc(*'DIVX')
        fname = os.path.dirname(sys.argv[0]) + "/stream.avi"
        video = cv.VideoWriter(fname, fourcc, 10.0, (frame_width, frame_height))
    
    screen_width = 640
    screen_height= 360

    cv.namedWindow(url, cv.WINDOW_NORMAL)
    cv.resizeWindow(url, screen_width, screen_height)
    
    # cv.namedWindow('edge', cv.WINDOW_NORMAL)
    # cv.resizeWindow('edge', screen_width, screen_height)
    
    vca_data = {'frame_cnt': 0, 'timestamp': 0, 'datetime': '', 'object_count': 0, 'data': []}
    ts = time.time() -3
    ts_vca = 0
    
    
    tflag = 0
    while Running:
        # ts_s =time.time()
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = ts + int(cap.get(cv.CAP_PROP_POS_MSEC))/1000

        # edge = cv.Canny(frame, 100, 100)
        # cv.imshow('edge', edge)

        if (not q.empty()):
            (ts_vca, vca_data)= q.get()

        plot_bbox(vca_data, frame, (frame_width, frame_height), line_thickness=None)

        tl = round(0.002 * (frame.shape[0] + frame.shape[1]) / 2) + 1  # line/font thickness
        tf = max(tl - 1, 1)  # font thickness

        cv.putText(frame, "%.3f, %.3f, %.3f" %(timestamp, ts_vca, (ts_vca- timestamp)), (10, 100), 0, tl / 3, (225, 0, 0), thickness=tf, lineType=cv.LINE_AA)

        if RECORD:
            if tflag %3 == 0:
                video.write(frame)
            
        tflag = (tflag + 1)%3
        
        cv.imshow(url, frame)
        
        
        ch = cv.waitKey(1) &0xFF
        if ch == 27 or ch == ord('q') or ch == ord('Q'):
            Running = False
            break

    for i in range(30):
        if not q.empty():
            q.get()
    
    Running = False
    cap.release()
    if RECORD:
        video.release()
    cv.destroyAllWindows()


if __name__ == "__main__":
    url_video = "rtsp://%s:%d/ufirststream" %(dev_ip, rtsp_port)
    url_vca = "http://%s:%d/uapi-cgi/metastream.cgi" %(dev_ip, http_port)
    
    q_vca_t   = queue.Queue(30)
    q_frame_t = queue.Queue(60)

    th_vca =  threading.Thread(target=getVCAdata, args =(url_vca, q_vca_t,))
    th_vca.start()
    
    th_vca =  threading.Thread(target=grabVideo,  args =(url_video, q_frame_t,))
    th_vca.start()
    

    th_vca =  threading.Thread(target=showVideoVCA,  args =(q_frame_t, q_vca_t))
    th_vca.start()

    
    
    
    q_vca_t.join()
    q_frame_t.join()
    
    sys.exit()
    th_video = threading.Thread(target=showVideo, args=(url_video, q_frame,))
    th_video.start()

    # q.join()

    sys.exit()

    response = requests.get(url_vca, stream=True)
    cap = cv.VideoCapture(url_video)
    if cap.isOpened():
        ret, frame = cap.read()
        while not ret:
            ret, frame = cap.read()
    else :
        cap.release()
        sys.exit()

    frame_width  = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    timestamps   = int(cap.get(cv.CAP_PROP_POS_MSEC))

    screen_width = 640
    screen_height= 360
    cv.namedWindow(url_video, cv.WINDOW_NORMAL)
    cv.resizeWindow(url_video, screen_width, screen_height)

    message_str = ''
    vca_data = {'frame_cnt': 55575, 'timestamp': 1667195110.196, 'datetime': '2022-10-31 13:45:10', 'object_count': 1, 'data': [{'cat_no': 62, 'cat_item': 'tv', 'score': 79.84, 'pos_lt': [1228, 35020], 'pos_rb': [15359, 54475], 'pos_cen': [8293, 44747], 'width': 14131, 'height': 19455}]}
    for content in response.iter_content(chunk_size=1):
        ret, frame = cap.read()
        if not ret:
            break

        if content == b'@':
            vca_data = json.loads(message_str)
            message_str = ''

        print (vca_data['frame_cnt'])
        for data in vca_data['data'] :
            x0 = frame_width * data['pos_lt'][0] // 0xFFFF
            y0 = frame_height * data['pos_lt'][1] // 0xFFFF
            x1 = frame_width * data['pos_rb'][0] // 0xFFFF
            y1=  frame_height * data['pos_rb'][1] // 0xFFFF

            plot_one_box((x0,y0,x1,y1), frame, color=None, label=data['cat_item'], line_thickness=None)


        cv.imshow(url_video, frame)
        ch = cv.waitKey(1) &0xFF
        if ch == 27 or ch == ord('q') or ch == ord('Q'):
            Running = False
            break
sys.exit()




class LoadStreams:  # multiple IP or RTSP cameras
    def __init__(self, s='streams.txt', img_size=640):
        self.img_size = img_size
        self.capture = None
        self.Running = True

        cap = cv.VideoCapture(eval(s) if s.isnumeric() else s)

        assert cap.isOpened(), 'Failed to open %s' % s
        w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv.CAP_PROP_FPS) % 100
        _, self.imgs = cap.read()  # guarantee first frame
        thread = threading.Thread(target=self.update, args=(cap,), daemon=True)
        print('success (%gx%g at %.2f FPS).' % (w, h, fps))
        thread.start()
        print('')  # newline
        self.capture = cap

    def update(self, cap):
        while cap.isOpened() and self.Running:
            cap.grab()
            _, self.imgs = cap.retrieve()
            time.sleep(0.01)  # wait time

    def __iter__(self):
        self.count = -1
        return self

    def __next__(self):
        self.count += 1
        # img = self.imgs.copy()
        if cv.waitKey(1) == ord('q'):  # q to quit
            self.capture.release()
            print("raise stopiteration")
            raise StopIteration

        # return img 
        return self.imgs

    def __len__(self):
        return 0  # 1E12 frames = 32 streams at 30 FPS for 30 years

    def stop(self):
        self.Running = False
        print("stop!")

Running = True
url = "rtsp://192.168.1.209:554/ufirststream"
d = LoadStreams(url)

root = Tk()

try :
    for frame_idx, img in enumerate(d):
        cv.imshow(str(url), img)
except:
    d.stop()


root.mainloop()



sys.exit()
# sample of avstream by updtechnology
# The user must install the requests packages using pip
import json
import requests


def do_something_useful(message):
    metadata = json.loads(message)
	# Metadata is located under the key 'value0'
    metadata = metadata['value0']
    print('Received metadata')
    print(json.dumps(metadata, indent=4, sort_keys=True))


if __name__ == '__main__':
	IP_ADDRESS = '192.168.2.25'
	STREAM_ID = 'first'
	USER_ID = 'root'
	USER_PASSWORD = 'Admin1234'
	OUTPUT_FORMAT = 'json'
  
	response = requests.get(f'http://{IP_ADDRESS}/nvc-cgi/avstream.cgi?streamno={STREAM_ID}&streamreq=meta&format={OUTPUT_FORMAT}',
					stream=True, auth=(USER_ID, USER_PASSWORD))

	char_count = 0
	message_type = 0
	message_str = ''
	for content in response.iter_content(chunk_size=1):
		char_count += 1
		# The first part of stream is AV stream header which is 96 bytes long.
		if message_type == 0 and char_count >= 96:
			message_type = 1
			char_count = 0
		elif message_type == 1:
			# The second part of stream is VCA metadata. The first part of stream starts with '@'.
			if content == b'@':
				# 
				do_something_useful(message_str)
				message_str = ''
				message_type = 0
				char_count = 1
			else:
				# Concatenates read byte
				message_str += str(content, "utf-8")


