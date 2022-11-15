import time, os, sys
import json
import cv2 as cv
import requests
import numpy as np
import multiprocessing


Running = True
def putQueue(url, q):
    print ("PUTQUEUE")
    global Running, dev_ip, http_port

    message_str = ''
       
    print(url)
    response = requests.get(url,stream=True) 
    
    for content in response.iter_content(chunk_size=1):
        if not Running:
            return 0
        if content == b'@':
            vca_data = json.loads(message_str)
            q.put(vca_data)
            # print (message_str)
            message_str = ''
        else:
            message_str += str(content, "utf-8")     
   
    Running = False

def getQueue(url, q):
    global Running, dev_ip, http_port
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
    timestamps   = int(cap.get(cv.CAP_PROP_POS_MSEC))

    screen_width = 640
    screen_height= 360
    cv.namedWindow(url, cv.WINDOW_NORMAL)
    cv.resizeWindow(url, screen_width, screen_height)

    while Running:
        ret, frame = cap.read()
        if not ret:
            break

        data = q.get()
        timestamp = int(cap.get(cv.CAP_PROP_POS_MSEC))
        print ("vca frame:%d, timestamp:%d, vca_timestamp:%.3f" %(data['frame_cnt'], timestamp, data['timestamp']))
        # for dd in data['data'] :
        #     x0 = frame_width * dd['pos_lt'][0] // 0xFFFF
        #     y0 = frame_height* dd['pos_lt'][1] // 0xFFFF
        #     x1 = frame_width * dd['pos_rb'][0] // 0xFFFF
        #     y1 = frame_height* dd['pos_rb'][1] // 0xFFFF

        #     plot_one_box((x0,y0,x1,y1), frame, color=None, label=dd['cat_item'], line_thickness=None)

        cv.imshow(url, frame)
        ch = cv.waitKey(1) &0xFF
        if ch == 27 or ch == ord('q') or ch == ord('Q'):
            Running = False
            break

    cap.release()
    cv.destroyAllWindows()

dev_ip = "192.168.1.209"
rtsp_port = 554
http_port = 80

if __name__ == "__main__":
    q = multiprocessing.Queue()
    # pipeB = multiprocessing.Pipe()
    url_vca = "http://%s:%d/uapi-cgi/metastream.cgi" %(dev_ip, http_port)
    thread_one = multiprocessing.Process(target=putQueue, args=(url_vca, q))

    url_video = "rtsp://%s:%d/ufirststream" %(dev_ip, rtsp_port)
    thread_two = multiprocessing.Process(target=getQueue, args=(url_video, q,))

    thread_one.start()
    thread_two.start()

    thread_one.join()
    thread_two.join()