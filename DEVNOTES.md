
It seems it you try to send too much data at once, it gets reported by send_nsca as having been sent successfully, but fails on the server end. If you turn on debugging, you see, e.g.:

```
Feb 12 19:40:40 mon04 nsca[2161]: Dropping packet with invalid CRC32 - possibly due to client using wrong password or crypto algorithm?
```

Trying out a few things, sending 2 messages at a time succeeded, but 12 at a time failed. It's probably not worth splitting them for that little parallelism, so maybe you just have to send them each individually?




...




Argh, it looks like even doing 2 at a time, the messages aren't getting interpreted correctly? Or at least, they're not making it to the Icinga services.

I'm trying 1 at a time to see if that works, using split on a saved file of messages.

... Does send_nsca fork? It seems to be making lots of connections at once, and I'm not sure if that's just how it's logging the write aggregation.



---

Making the versions match seems to have made the CRC problems go away, and the updated send_nsca help message mentions that actually you need ^W to separate lines, not a newline, because that makes sense :rage:

Anyway, now my problem is that it times out after 10 seconds of transmitting regardless to whether traffic is still being sent

FFS



