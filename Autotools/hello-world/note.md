# workflow
1. create project with
    - configure.ac
    - Makefile.am
    - src/Makefile.am
    - src/*
2. `autoreconf -i` (or --install)
    + this generates stuffs needed to build package
3. `./configure` 
    + generates Makefile, config.h (used to store flags about the system)
4. `make`

# common make targets
- `make` - build everything
- `make install`
- `make clean` - clean build files in src
- `make distclean` - clean build files and generated config files
