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
import bitstring
# from tkinter import *

dev_ip = "192.168.1.28"
rtsp_port = 554
http_port = 80
fname = os.path.dirname(sys.argv[0]) + "/stream.h264"

def sendNrecv(s, mesg, length=4096):
    print("\n***** send *****\n %s\n" %mesg)
    s.send(mesg)
    recst = s.recv(length)
    print("***** recv *****")
    for line in recst.splitlines():
        print(line.decode())
    return recst

def getSessionId(st):
	for rec in st.splitlines():
		ss = rec.split()
		if (ss[0].strip()==b"Session:"):
			ssid = (ss[1].split(b";")[0].strip())
			return ssid


def getPorts(searchst, st):
    """ Searching port numbers from rtsp strings using regular expressions
    """
    st = st.decode()
    pat=re.compile(searchst+"=\d*-\d*")
    pat2=re.compile('\d+')
    mstring=pat.findall(st)[0] # matched string .. "client_port=1000-1001"
    nums=pat2.findall(mstring)
    numas=[]
    for num in nums:
        numas.append(int(num))
    return numas

# digest packet start 
def digestpacket(st):
	""" This routine takes a UDP packet, i.e. a string of bytes and ..
	(a) strips off the RTP header
	(b) adds NAL "stamps" to the packets, so that they are recognized as NAL's
	(c) Concantenates frames
	(d) Returns a packet that can be written to disk as such and that is recognized by stock media players as h264 stream
	"""
	startbytes = b"\x00\x00\x00\x01" # this is the sequence of four bytes that identifies a NAL packet.. must be in front of every NAL packet.
	bt = bitstring.BitArray(bytes=st) # turn the whole string-of-bytes packet into a string of bits.  Very unefficient, but hey, this is only for demoing.
	# lc=12   # bytecounter
	# bc=12*8 # bitcounter

	version 	= bt[0:2].uint 	# version
	p 			= bt[3] 		# P
	x 			= bt[4] 		# X
	cc 			= bt[4:8].uint 	# CC
	m 			= bt[9] 		# M
	pt 			= bt[9:16].uint # PT
	sn 			= bt[16:32].uint# sequence number
	timestamp 	= bt[32:64].uint# timestamp
	ssrc 		= bt[64:96].uint# ssrc identifier
	# The header format can be found from: https://en.wikipedia.org/wiki/Real-time_Transport_Protocol

	# print ("version %d" %(version))
	lc=12 # so, we have red twelve bytes
	bc=12*8 # .. and that many bits

	#   print ("version, p, x, cc, m, pt",version,p,x,cc,m,pt)
	#   print ("sequence number, timestamp",sn,timestamp)
	#   print ("sync. source identifier",ssrc)

	# st=f.read(4*cc) # csrc identifiers, 32 bits (4 bytes) each
	cids=[]
	for i in range(cc):
		cids.append(bt[bc:bc+32].uint)
		bc += 32
		lc += 4
	# print ("csrc identifiers:",cids)

	if (x): # this section haven't been tested.. might fail
		hid = bt[bc:bc+16].uint
		bc += 16
		lc += 2

		hlen = bt[bc:bc+16].uint
		bc += 16
		lc += 2
		print ("ext. header id:%d, header len:%d" %(hid,hlen))

		hst = bt[bc:bc+32*hlen]
		bc += 32*hlen
		lc += 4*hlen

	# now we enter the NAL packet, as described here: https://tools.ietf.org/html/rfc6184#section-1.3
	# Some quotes from that document:
	"""
	5.3. NAL Unit Header Usage

	The structure and semantics of the NAL unit header were introduced in Section 1.3.  For convenience, the format of the NAL unit header is reprinted below:
		+---------------+
		|0|1|2|3|4|5|6|7|
		+-+-+-+-+-+-+-+-+
		|F|NRI|  Type   |
		+---------------+
	This section specifies the semantics of F and NRI according to this specification.
	"""
	"""
	Table 3.  Summary of allowed NAL unit types for each packetization mode (yes = allowed, no = disallowed, ig = ignore)
		Payload Packet    Single NAL    Non-Interleaved    Interleaved
		Type    Type      Unit Mode           Mode             Mode
		-------------------------------------------------------------
		0      reserved      ig               ig               ig
		1-23   NAL unit     yes              yes               no
		24     STAP-A        no              yes               no
		25     STAP-B        no               no              yes
		26     MTAP16        no               no              yes
		27     MTAP24        no               no              yes
		28     FU-A          no              yes              yes
		29     FU-B          no               no              yes
		30-31  reserved      ig               ig               ig
	"""
	# This was also very usefull: http://stackoverflow.com/questions/7665217/how-to-process-raw-udp-packets-so-that-they-can-be-decoded-by-a-decoder-filter-i A quote from that:
	"""
	First byte:  [ 3 NAL UNIT BITS | 5 FRAGMENT TYPE BITS] 
	Second byte: [ START BIT | RESERVED BIT | END BIT | 5 NAL UNIT BITS] 
	Other bytes: [... VIDEO FRAGMENT DATA...]
	"""

	fb = bt[bc] # i.e. "F"
	nri = bt[bc+1:bc+3].uint # "NRI"
	nlu0 = bt[bc:bc+3] # "3 NAL UNIT BITS" (i.e. [F | NRI])
	typ = bt[bc+3:bc+8].uint # "Type"
	#   print ("F, NRI, Type :", fb, nri, typ)
	#   print ("first three bits together :",bt[bc:bc+3])

	if (typ==7 or typ==8):
	# this means we have either an SPS or a PPS packet. they have the meta-info about resolution, etc. more reading for example here:  http://www.cardinalpeak.com/blog/the-h-264-sequence-parameter-set/
		# if (typ==7):
		# 	print (">>>>> SPS packet")
		# else:
		# 	print (">>>>> PPS packet")
		return startbytes+st[lc:]
	# .. notice here that we include the NAL starting sequence "startbytes" and the "First byte"

	bc += 8
	lc += 1 # let's go to "Second byte"
	# ********* WE ARE AT THE "Second byte" ************
	# The "Type" here is most likely 28, i.e. "FU-A"
	start = bt[bc] # start bit
	end   = bt[bc+2] # end bit
	nlu1  = bt[bc+3:bc+8] # 5 nal unit bits

	if (start): # OK, this is a first fragment in a movie frame
		# print (">>> first fragment found")
		nlu=nlu0+nlu1 # Create "[3 NAL UNIT BITS | 5 NAL UNIT BITS]"
		head= startbytes+nlu.bytes # .. add the NAL starting sequence
		lc+=1 # We skip the "Second byte"
	if (start==False and end==False): # intermediate fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
		head=b""
		lc+=1 # We skip the "Second byte"
	elif (end==True): # last fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
		head=b""
		# print ("<<<< last fragment found")
		lc+=1 # We skip the "Second byte"

	if (typ==28): # This code only handles "Type" = 28, i.e. "FU-A"
		return head+st[lc:]
	else:
		raise(Exception,"unknown frame type for this piece of s***")

#end digest packet



def grabRtsp(dev_ip, rtsp_port):
	descr=("DESCRIBE rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 0\r\nUser-Agent: python\r\nAccept: application/sdp\r\n\r\n" %(dev_ip,rtsp_port)).encode()
	optio=("OPTIONS rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 2\r\nUser-Agent: python\r\n\r\n"  %(dev_ip,rtsp_port)).encode()
	# setu =("SETUP rtsp://%s:554/ufirststream/trackID=0 RTSP/1.0\r\nCSeq: 2\r\nUser-Agent: python\r\nTransport: RTP/AVP;unicast;client_port=8084-8085\r\n\r\n" %dev_ip).encode()
	#[OK with Nais] setu =("SETUP rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 3\r\nUser-Agent: python\r\nTransport: RTP/AVP;unicast;client_port=60784-60785\r\n\r\n" %(dev_ip,rtsp_port)).encode()
	setu =("SETUP rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 3\r\nUser-Agent: python\r\nTransport: RTP/AVP;unicast;client_port=1000-1001\r\n\r\n" %(dev_ip,rtsp_port)).encode()
	play =("PLAY rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 5\r\nUser-Agent: python\r\nSession: SESID\r\nRange: npt=0.000-\r\n\r\n" %(dev_ip,rtsp_port)).encode()
	teard=("TEARDOWN rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 7\r\nUser-Agent: python\r\nSession: SESID\r\n\r\n" %(dev_ip,rtsp_port)).encode()
	getpa=("GET_PARAMETER rtsp://%s:%d/ufirststream RTSP/1.0\r\nCSeq: 9\r\nUser-Agent: python\r\nSession: SESID\r\n\r\n" %(dev_ip,rtsp_port)).encode()

	s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.connect((dev_ip,554)) # RTSP should peek out from port 554

	sendNrecv(s, descr)
	sendNrecv(s, optio)
	recs = sendNrecv(s, setu )
	ssid = getSessionId(recs)
	# server_port = getPorts("server_port", recs)
	client_port = getPorts("client_port", recs)
	# print("server port:%s, client_port: %s" %(server_port, client_port))

	para = getpa.replace(b"SESID", ssid)
	sendNrecv(s, para )

	s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s1.bind(("", client_port[0])) # we open a port that is visible to the whole internet (the empty string "" takes care of that)
	s1.settimeout(5) # if the socket is dead for 5 s., its thrown into trash

	play = play.replace(b"SESID", ssid)
	# print(play)
	sendNrecv(s, play )

	with open(fname, "wb") as f:
		for i in range (10):
			recst=s1.recv(4096)
			st = digestpacket(recst)
			f.write(st)
			print("%d=>%d" %(len(recst), len(st)))


	teard = teard.replace(b"SESID", ssid)
	sendNrecv(s, teard )

	s1.close()
	s.close()






if __name__ == "__main__":

    url_video = "rtsp://%s:%d/ufirststream" %(dev_ip, rtsp_port)
    url_vca = "http://%s:%d/uapi-cgi/metastream.cgi" %(dev_ip, http_port)
    grabRtsp(dev_ip, rtsp_port)
   
