import os
import sys
import importlib

# simple test application that runs ggoutlier from this plugin
# This is made slightly complicated as ggoutlier doesn't include its
# own setup.py, and therefore importing it and having it import its
# own modules require a workaround
def main():
    # get the location of the ggoutlier module before importing
    # if we attempt to import first it will fail as it's unable to
    # import other modules it defines
    fn = importlib.machinery.PathFinder().find_module("ggoutlier").get_filename()
    path = os.path.dirname(fn)
    print("ggoutlier module path")
    print(path)
    # add the ggoutlier folder to the Python system search path
    # so that other ggoutlier modules can be imported
    sys.path.append(path)

    # now import ggoutlier
    from ggoutlier import ggoutlier
    ggoutlier.main(['--help'])


if __name__ == '__main__':
    main()
