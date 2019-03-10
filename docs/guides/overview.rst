Overview
========

.. contents:: Contents

Project structure
-----------------
Some not-so-self-explanatory directories:

* ``.docker``
    Files which are used in the Docker container.

* ``data``
    Various data used by grobber which should not be inside of the code.

* ``grobber``
    Python source files which power Grobber

Code structure
^^^^^^^^^^^^^^
The code itself is neatly categorised within several folders.
The Quart application resides in the ``app.py`` file, but most
of the routes are stored in blueprints which can be found in the
``blueprints`` directory.


Glossary
--------
.. glossary::

    Source
        A source is an interface between an SourceAnime streaming website and Grobber.
        It extracts metadata and episodes from such a site and provides a search
        functionality.

    Embedded stream
        An embedded stream is an external player for an episode video.
        This website can be embedded in an iFrame.

    Stream
        A handler for an :term:`Embedded stream` which can extract the video source (i.e. file)
        from it.

    UID
        All Grobber items have a unique id "UID". This uid can be used to target the given item and also
        contains a lot of information in it.