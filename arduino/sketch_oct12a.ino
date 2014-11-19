#include <Bridge.h>
#include <Console.h>
#include <FileIO.h>
#include <HttpClient.h>
#include <Mailbox.h>
#include <Process.h>
#include <YunClient.h>
#include <YunServer.h>

#include <Arduino.h>
#include "wiegand.h"

WIEGAND wg;

void setup() {
  
  pinMode(6, OUTPUT);
  pinMode(4, OUTPUT);
  
  digitalWrite(6, LOW);
  digitalWrite(4, LOW);
 
  wg.begin();
  Bridge.begin();
  Mailbox.begin();
  //Process access;
  
  //access.begin("/mnt/sda1/ac/bin/access.py");
  //access.runAsynchronously();
  
}

void loop() {

  //int i = 0;
  
  if(wg.available())
    {
        unsigned int wcode = wg.getCode();
        Bridge.put("CODE", String(wcode));    
    }
  while (Mailbox.messageAvailable()) {
        String message;
        Mailbox.readMessage(message);
        if (message == "O") {
           digitalWrite(6, HIGH);
           digitalWrite(4, HIGH);
           delay(100);
           digitalWrite(6, LOW);
           delay(400);
           digitalWrite(4, LOW);
        }

  }       
 
}
