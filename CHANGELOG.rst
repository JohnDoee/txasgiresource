Changelog
=========

Version 2.2.1 (07-05-2020)
-----------------------------------------------------------

*   Fixed memoryleak regarding websocket timeout and
    lack of application cleanup
*   Fixed bug related to shown exception on sendfile

Version 2.2.0 (17-02-2020)
-----------------------------------------------------------

*   Added support for asgi3

Version 2.1.7 (21-12-2018)
-----------------------------------------------------------

*   Fixed hanging request related to sendfile

Version 2.1.6 (15-07-2018)
-----------------------------------------------------------

*   Added support for subprotocols

Version 2.1.5 (17-05-2018)
-----------------------------------------------------------

*   Added support for automatic reverse proxy mode for
    private networks

Version 2.1.4 (02-05-2018)
-----------------------------------------------------------

*   Fixed small bug with x-sendfile and HEAD request

Version 2.1.3 (02-05-2018)
-----------------------------------------------------------

*   Missing return

Version 2.1.2 (02-05-2018)
-----------------------------------------------------------

*   Fixed some code paths that could result in errors.

Version 2.1.1 (01-05-2018)
-----------------------------------------------------------

*   Fixed small bug with double-installation of reactor.

Version 2.1.0 (29-04-2018)
-----------------------------------------------------------

*   Updating to support Channels 2.1.0 and the upcoming
    ASGI spec changes (run application initialization in a thread)

Version 2.0.1 (27-04-2018)
-----------------------------------------------------------

*   Changed (defer) timeout to use built-in timeout exceptions
    and system
*   Fixed small bugs when requests did not behave as normal.

Version 2.0.0 (05-02-2018)
-----------------------------------------------------------

*   Updated to channels 2 way-of-working

Version 0.4.1 (03-12-2017)
-----------------------------------------------------------

*   Fixed small bug with proto forward header

Version 0.2.2 (28-03-2017)
-----------------------------------------------------------

*   Added workaround for Direct SSL problem using proxyheader

Version 0.2.1 (20-03-2017)
-----------------------------------------------------------

*   Fixed small bug with scheduler loop
*   Made sure package is installable

Version 0.2.0 (03-02-2017)
-----------------------------------------------------------

*   Added websocket accept support
*   Renamed more_body to body_channel

Version 0.1.0 (02-10-2016)
-----------------------------------------------------------

*   Initial release
