#!/usr/bin/python

import sys
import email
import cass
import os
import time
import hashlib
#import StringIO
from email.errors import NoBoundaryInMultipartDefect

#from email.Iterators import _structure
#from email.iterators import body_line_iterator
#from email.utils import parseaddr
#from email.utils import getaddresses


##################################
## TODO:
##     data expiration (?)
##     
##
## FIXED:
##    windows/unix newline
##    newlines in txt attachment fixed
##    mime body headers with FOLDING 


class BufferedData():
    
    def __init__(self, f):            
            self.lines = []            
            self.newlineStack = []
            self.f = f
            
    def readline(self):        
        if not self.lines:
            line = self.f.readline()
            line = line.replace('\r\n', '\n').replace('\r', '\n')
       
        else:
            line = self.lines.pop()
        
        return line
    
    def fakeNewLine(self):        
        self.newlineStack.append('\n')

    
    def unreadline(self, line):
        self.lines.append(line)

###############################################################################
def rawHeader(key, msg):
    header = []
    
    while True:
        line = msg.readline()
        line = line.replace('\r\n', '\n').replace('\r', '\n')
      
        header.append(line)
      
        if line == '\n':
            break
 
    return ''.join(header)    
#
def rawBody(key, email):    
    body = []
    
    while True:
        line = email.readline()
        line = line.replace('\r\n', '\n').replace('\r', '\n')
        
        body.append(line)
        
        if len(line) == 0:
            break #EOF
            
    return ''.join(body)    
#    
def getMetaData(msg):    
    #the real recipient is in the email header, because of tapping
    #X-VF-Scanner-Rcpt-To: x@y
    #TODO:??? normally its in envelope
    uid = msg.get('X-VF-Scanner-Rcpt-To')
    
    if uid == None:
        uid = 'charvat@cvut1.centrum.cz'
    
    #TODO:??? whats the domain format, fix for fulltext? 
    domain = uid.partition('@')[2]

    #From field in email header is mandatory by RFC2822
    eFrom = msg.get('From')
    
    if eFrom == None:
        eFrom = ''

    #Date field in email header is mandatory by RFC2822
    #format: Fri, 18 Mar 2011 16:30:00 +0000
    date = msg.get('Date')
    if date == None:
        date = ''
        
    subject = msg.get('Subject')
    if subject == None:
        subject = '' 
    
    return (uid, domain, eFrom, subject, date)
#    
def metaAttachment(msg, boundary, attach ,bSet):    
    if msg.is_multipart():
        if  (msg.get_content_maintype() == 'multipart'):
            boundary = msg.get_boundary()
            bSet.add('--' + boundary)
            bSet.add('--' + boundary + '--')
            
        for subpart in msg.get_payload():
            metaAttachment(subpart, boundary, attach, bSet)
  
    
    if (msg.get_content_type() != 'text/plain' and msg.get_content_type() != 'text/html' and
            msg.get_content_maintype() != 'multipart' and msg.get_content_maintype() != 'message' and 
            msg.get_content_type() != 'message/rfc822'):
                
        boundary = '--' + boundary
        
        try:                            
            fileName = str(msg.get_filename())                
        except UnicodeEncodeError:                
            fileName = msg.get_filename().encode('utf8')
        
        #size + hash
        attach.append((boundary, msg.get_content_type(), fileName))        
#        
def writeAttachment(data):
    
    #??? for sure sha1
    m = hashlib.sha1()      
    m.update(data)
    key = m.hexdigest()
    
    #print key
    cass.writeAttachment(key, data)                                 
    return key 
#



def newRawBody(key, f, attachments, bSet):    
   
    stat = 6;

    #print attachments
    
    buff = BufferedData(f)    
    data = []
    body = []
    bound = ()
    attchList = []
    
    while True:       
        if stat == 0:                   
            #print "Stat:0"
            while True:
                line = buff.readline()
                body.append(line)
                #print line,
                if line[0:len(line) - 1] == bound[0]:                        
                    #possible attach boundary       
                    #print line               
                    stat = 1
                    break
        #automata start                        
        elif stat == 6:
            #print "Stat:6"            
            if attachments:
                bound = attachments.pop(0)                
                stat = 0
            else:                
                #read end of the email
                stat = 5         
        #attachment header
        elif stat == 1:
            #print "Stat:1"
            fold = 0
            #??? fix that dirt...bez rozdielu ci som v spravnom headri tak dojdi ho az do konca? 
            while True:
                #print '>>>>'
                line = buff.readline()
                #print line, 
                body.append(line)                
                #is there content-type? / some emails use diff case of content-type
                if 'content-type:' in line.lower():
                    
                    if bound[1] in line.lower():
                        
                        stat = 10
                        break
                    #else:                        
                    #    stat = 0
                    #break
                    else:
                        #print 'folding'
                        #possible folding in header field                        
                        while True:
                            line = buff.readline()
                            
                            #folding
                            #print repr(line[0]),
                            if line[0] == '\t' or line[0] == ' ':
                                
                                
                                body.append(line)
                                
                                #     print 'bound:' + bound[1]
                                #     print line
                                if bound[1] in line.lower():
                                    #        print 'yup'
                                    stat = 10
                                    fold = 1
                                    break
                                else:
                                    break
                            else:                                
                                break
                            
                            buff.unreadline(line)
                         
                        #print fold
                         
                if line == '\n':
                    stat = 0            
                    break                
                elif fold == 1:
                    stat = 10
                    break
        #read rest of the header for selected attachment        
        elif stat == 10:
            #print "Stat:10"
            while True:                
                line = buff.readline()                
                body.append(line)                
                                
                if line == '\n':
                    stat = 2
                    break
            #print line
        #attachment body (data)
        elif stat == 2:   
            #print "Stat:2"     
            while True:
                line = buff.readline()
                """
                if 'A###' in line:
                    print "A## read" 
                    print repr(line)
                """
                if line == '\n':
                    #print repr(line)
                    buff.fakeNewLine()
                    #print buff.newlineStack
                    stat = 3
                    break
                elif line[0:len(line)-1] in bSet:
                    buff.unreadline(line)
                    stat = 4
                    break
                else:
                    data.append(line)
            prevStat = 2
            #print line
                       
        elif stat == 3:
            #print "Stat:3"          
            while True:                
                line = buff.readline()
                #print repr(line)
                if line == '\n':                    
                    buff.fakeNewLine()
                    #print buff.newlineStack
                elif line[0:len(line)-1] in bSet:
                    buff.unreadline(line)
                    stat = 4
                    break
                else: #text
                    #print 'TEXT?'
                    #print repr(line)
                    
                    stat = 2
                    break            
            
            #print 'cistim stack:' + str(len(buff.newlineStack))
            body2 = []
            #print "stack:"     
            #print buff.newlineStack       
            for newLine in buff.newlineStack:
                #print 'for'
                
                if stat == 4:                    
                    body2.append(newLine)                                        
                else:
                    #do 2ky
                    #print 'do 2'
                    data.append(newLine)
                #buff.newlineStack.pop()
                
            buff.newlineStack = []        
            if stat == 2:
                data.append(line)
            #print 'opustam 3'
            prevStat = 3
        elif stat == 4:
            #print "Stat:4"          
            
            #ddata = ''.join(data)  
            attKey = writeAttachment(''.join(data))                
            hash = 'DEDUPLICATION:' + attKey + '\n'
            
            ###body.append(hash) uncomment
            
            body.append(''.join(data))
                            
            
            #print ''.join(data)
            #print '>>>>>>>>>>>>>>>>>>'
                
            #(name, size, hash), its metadata for messageMetaData CF
            #metaData  = (bound[2], len(ddata), attKey)
            metaData  = (bound[2], len(''.join(data)), attKey)
            attchList.append(metaData)
            
            data = []
            
            if prevStat == 3:
                for newLines in body2:
                    body.append(newLines)
                                                
            stat = 6
        elif stat == 5:
            #print "Stat:5"
            while True:
                line = buff.readline()            
            
                if len(line) == 0:
                    break #EOF
                   
                body.append(line)
                            
            break
                    
    return (''.join(body), attchList)
#
def mimeEmail(key, f, msg, envelope, size):
       
    header = rawHeader(key, f)
    #print header,
    metaData = getMetaData(msg)  
    
    #find attachment's boundary and write attachments
    attachments = []
    bSet = set()

    metaAttachment(msg, 0, attachments, bSet)

    if len(attachments) != 0:
        #print attachments
        (body, attach) = newRawBody(key, f, attachments, bSet)
        #print header,
        #print body,
    #no attach to deduplicate
    else:
        body = rawBody(key, f)    
    #time of email parsing
    #return duration
    
    cass.writeMetaData(key, envelope, header, size, metaData, attach)    
    cass.writeContent(key, body)
# 
def rawEmail(key, f, msg, envelope, size):
    
    header = rawHeader(key, f)
    body = rawBody(key, f)
    metaData = getMetaData(msg)        
    #attch = []
       
    cass.writeMetaData(key, envelope, header, size, metaData, [])
    cass.writeContent(key, body)
##############################################################################


#??? whats the email key?
def parseEmail(emailFile):
    
    start = time.time()

    f = open(emailFile, 'r')
    msg = email.message_from_file(f)
    f.seek(0)

    env = open(emailFile + '.envelope', 'r')
    envelope = env.readline()
    env.close()

    size = os.path.getsize(emailFile)

    try:  
        if msg.is_multipart():
            mimeEmail(emailFile, f, msg, envelope, size)
        else:
            rawEmail(emailFile, f, msg, envelope, size)
        
    except NoBoundaryInMultipartDefect:
        rawEmail(emailFile, f, msg, envelope, size)
    

    f.close()

    duration = time.time() - start 
   
#    return duration

def main():
    
    email = sys.argv[1]
    start = time.time()
    
    parseEmail(email)
    
    
    duration = time.time() - start

    

if __name__ == '__main__':
    main()

