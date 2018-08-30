""" A file duplication/identity checker
"""

import setuptools

setuptools.setup(
    name='match',
    version='0.1.0.dev1',
    description=__doc__,
    author='Dylan Scott Grafmyre',
    author_email='dylan.grafmyre@gmail.com',
    py_modules=["match"],
    install_requires=['xxhash'],
    entry_points={
        'console_scripts': [
            'match=match:main',
        ],
    },
)

