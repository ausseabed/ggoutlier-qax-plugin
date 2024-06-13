from setuptools import setup

setup(
    name='ausseabed.ggoutlier',
    namespace_packages=['ausseabed'],
    version='0.0.1',
    url='https://github.com/ausseabed/ggoutlier-qax-plugin',
    author=(
        "Lachlan Hurst;"
    ),
    author_email=(
        "lachlan.hurst@gmail.com;"
    ),
    description=(
        'QAX Plugin for GGOutlier'
    ),
    entry_points={
        "gui_scripts": [],
        "console_scripts": [
            'run_ggoutlier = ausseabed.ggoutlier.qax.run_ggoutlier:main',
        ],
    },
    packages=[
        'ausseabed.ggoutlier',
        'ausseabed.ggoutlier.lib',
        'ausseabed.ggoutlier.qax'
    ],
    zip_safe=False,
    package_data={},
    install_requires=[
        'ausseabed.qajson',
        'ggoutlier'
    ],
    tests_require=['pytest'],
)
