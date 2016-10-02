txasgiresource
==============

txasgiresource is `ASGI <http://channels.readthedocs.io/en/latest/asgi.html>`_ implemented as a Twisted Web Resource,
very similar to `WSGIResource <http://twistedmatrix.com/documents/current/api/twisted.web.wsgi.WSGIResource.html>`_.

This is inspired by `Daphne <https://github.com/django/daphne/>`_ but largely implemented from specs.

It can also run as a daemon with or without the actual application embedded inside.

The code is available on `GitHub <https://github.com/JohnDoee/txasgiresource>`_

Usage
-----

As Twisted Resource
~~~~~~~~~~~~~~~~~~~
::

    from twisted.web import server

    from yourdjangoproject.asgi import channel_layer

    resource = ASGIResource(channel_layer)
    site = server.Site(resource)

    # If we are done with the resource, make sure to stop it.

    resource.stop()

As ASGI Protocol server
~~~~~~~~~~~~~~~~~~~~~~~
::

    twistd -n txasgi -c yourdjangoproject.asgi:channel_layer

As ASGI Protocol server with embedded workers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    twistd -n txasgi -c yourdjangoproject.asgi:channel_layer -w 6

As ASGI Protocol server with embedded workers and on a different port and ip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    twistd -n txasgi -c yourdjangoproject.asgi:channel_layer -w 6 -d tcp:5566:interface=0.0.0.0

Status
------

Master branch
~~~~~~~~~~~~~~
.. image:: https://coveralls.io/repos/github/JohnDoee/txasgiresource/badge.svg?branch=master
   :target: https://coveralls.io/github/JohnDoee/txasgiresource?branch=master
.. image:: https://travis-ci.org/JohnDoee/txasgiresource.svg?branch=master
   :target: https://travis-ci.org/JohnDoee/txasgiresource


Develop branch
~~~~~~~~~~~~~~
.. image:: https://coveralls.io/repos/github/JohnDoee/txasgiresource/badge.svg?branch=develop
   :target: https://coveralls.io/github/JohnDoee/txasgiresource?branch=develop
.. image:: https://travis-ci.org/JohnDoee/txasgiresource.svg?branch=develop
   :target: https://travis-ci.org/JohnDoee/txasgiresource

License
-------

MIT, see LICENSE