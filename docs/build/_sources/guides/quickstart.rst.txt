Quick-start
===========

.. contents:: Contents


Getting the code
----------------
You can simply grab the code from `GitHub <https://github.com/MyAnimeStream/grobber>`_.
Clone it, download the ZIP file, do whatever you want. As soon as you have the code
you have everything you need to get started.

Installing Dependencies
^^^^^^^^^^^^^^^^^^^^^^^
Grobber uses `Pipenv <https://pipenv.readthedocs.io>`_ to mangage its dependencies.
You can install Pipenv using ``pip install pipenv`` if you haven't already.
To install the dependencies for Grobber use the command ``pipenv install``.
That's it, you're done!

    You don't need to install the dependencies if you simply intend to run
    the server using Docker. However, if you're using a somewhat decent editor
    you'll want to install them for development.

Running Grobber
---------------
It is recommended that you use Docker for running Grobber. Even during development.

You may of course start the server using the command ``quart run`` by setting the
environment variable ``QUART_APP=grobber:app`` but keep in mind that this merely starts
Grobber and you have to provide all its dependencies like the MongoDB database...

It's much easier to use the provided ``docker-compose.yml`` file. It comes with all the necessary
dependencies and all you need to do to start the server is run ``docker-compose up -d --build``.
This will bind the Grobber server to the port 80. You can adjust this setting in the
``docker-compose.yml`` file.


Building the Documentation
--------------------------
The documentation is based on `Sphinx <http://www.sphinx-doc.org>`_ and can be built using
the command ``sphinx-build -b html docs/source docs/build``.
