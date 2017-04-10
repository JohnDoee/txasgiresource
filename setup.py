import os

from setuptools import setup

from txasgiresource import __version__

readme_path = os.path.join(os.path.dirname(__file__), "README.rst")
with open(readme_path) as fp:
    long_description = fp.read()

setup(
    name='txasgiresource',
    version=__version__,
    url='https://github.com/JohnDoee/txasgiresource',
    author='John Doee',
    author_email='johndoee@tidalstream.org',
    description='ASGI implemented as a Twisted resource',
    long_description=long_description,
    license='MIT',
    packages=['txasgiresource', 'txasgiresource.tests', 'twisted.plugins'],
    install_requires=[
        'asgiref>=1.1.0',
        'twisted>=16.0',
        'autobahn>=0.12',
        'apscheduler>=3.2.0',
        'six',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Framework :: Twisted',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
