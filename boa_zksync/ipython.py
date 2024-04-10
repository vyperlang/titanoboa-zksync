from IPython.core.magic import magics_class, line_cell_magic, cell_magic, line_magic, Magics

from boa_zksync.interpret import eval_zksync, loads_zksync_partial, loads_zksync


@magics_class
class TitanoboaZksyncMagic(Magics):
    @line_cell_magic
    def vyper(self, line, cell=None):
        if cell is None:
            return eval_zksync(line)
        return self.deployer(line, cell)

    # unsure about "vyper" vs "contract" cell magic; keep both until decided
    @cell_magic
    def deployer(self, line, cell):
        line = line or None
        c = loads_zksync_partial(cell, name=line)
        if line:
            self.shell.user_ns[line] = c  # ret available in user ipython locals
        return c

    @cell_magic
    def contract(self, line, cell):
        line = line or None
        c = loads_zksync(cell, name=line)
        if line:
            self.shell.user_ns[line] = c  # ret available in user ipython locals
        return c

    # unsure about "vyper" vs "eval" line magic; keep both until decided
    @line_magic
    def eval(self, line):
        return eval_zksync(line)


def load_ipython_extension(ipy_module):
    ipy_module.register_magics(TitanoboaZksyncMagic)
