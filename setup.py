from setuptools import setup

def readme():
    with open('README.md') as rm:
        return rm.read()

setup(
    name='sfrCore',
    version='0.0.1',
    description='Core database model and utilities for the SFR project',
    url='https://github.com/nypl/sfr-core',
    author='Michael Benowitz',
    author_email='michaelbenowitz@nypl.org',
    license='MIT',
    packages=['sfrCore'],
    install_requires=[
        'psycopg2-binary',
        'sqlalchemy',
        'python-dateutil',
        'requests',
        'pycountry'
    ],
    zip_safe=False
)