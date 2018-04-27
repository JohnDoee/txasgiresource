txasgiresource
==============

txasgiresource is `ASGI <http://channels.readthedocs.io/en/latest/asgi.html>`_ implemented as a Twisted Web Resource,
very similar to `WSGIResource <http://twistedmatrix.com/documents/current/api/twisted.web.wsgi.WSGIResource.html>`_.

This is inspired by `Daphne <https://github.com/django/daphne/>`_ but somewhat implemented from specs.

It can also run as a daemon.

The code is available on `GitHub <https://github.com/JohnDoee/txasgiresource>`_

Usage
-----

As Twisted Resource
~~~~~~~~~~~~~~~~~~~
.. code-block:: python

    from twisted.web import server

    from yourdjangoproject.routing import application

    resource = ASGIResource(application)
    site = server.Site(resource)

    # If we are done with the resource, make sure to stop it.

    yield resource.stop()

As ASGI Protocol server
~~~~~~~~~~~~~~~~~~~~~~~
::

    twistd -n txasgi -a yourdjangoproject.routing:application

As ASGI Protocol server on a different port and ip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
::

    twistd -n txasgi -a yourdjangoproject.asgi:channel_layer -d tcp:5566:interface=0.0.0.0

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