# GGOutlier QAX Plugin
QAX plugin implementation for GGOutlier

This repository contains only the code required for GGOutlier to be integrated within QAX, the source code for GGOutlier can be found [here](https://github.com/pktrigg/ggoutlier).

> GGOutlier is a tool developed by Guardian Geomatics to Quality Control processed a multibeam bathymetry surface, and validate a processed depth surface against a standard such as those published by IHO SP44 or HIPP.

More details on GGOutlier and its use independent of QAX can be found in the [readme](https://github.com/pktrigg/ggoutlier/blob/main/README.md).


## Getting started

There's no use case for using the contents of this repository outside QAX. To use GGOutlier refer to the instructions included in the links above. The following is a getting started guide for developers wishing to further develop the QAX GGOutlier plugin.

This repository pulls in GGOutlier as a submodule, therefore the following commands must be run to clone the repository and submodule.

    git clone https://github.com/ausseabed/ggoutlier-qax-plugin.git
    cd ggoutlier-qax-plugin
    git submodule init
    git submodule update

Now install the module. It's recommended to use the `-e` arguement to support development.

    pip install -e .

A small test command application has been included that will run GGOutlier passing it a single `--help` arguement. This perform a **minimal** check that GGOutlier and its dependencies are installed correctly.

    run_ggoutlier

