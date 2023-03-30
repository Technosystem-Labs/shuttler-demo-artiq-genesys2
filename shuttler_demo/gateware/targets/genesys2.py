import argparse

from misoc.integration.builder import builder_args, builder_argdict
from misoc.integration.soc_sdram import *
from misoc.cores import gpio

from artiq.gateware.targets.digilent_genesys2 import _StandaloneBase
from artiq.gateware import rtio
from artiq.build_soc import *

from shuttler_demo.gateware.cores.shuttler import Shuttler


class TestVariant(_StandaloneBase):
    def __init__(self, gateware_identifier_str=None, **kwargs):
        _StandaloneBase.__init__(
            self,
            fmc1_vadj=1.8,
            gateware_identifier_str=gateware_identifier_str, 
            **kwargs)

        self.rtio_channels = []
        Shuttler.add_std(self, fmc=1, iostd={
            "LA": self.platform.iostd[1.8],
            "HA": self.platform.iostd[1.8],
            "HB": self.platform.iostd[1.8]
        })

        i2c = self.platform.request("fmc1_osc_i2c")
        self.submodules.i2c = gpio.GPIOTristate([i2c.scl, i2c.sda])
        self.csr_devices.append("i2c")
        self.config["I2C_BUS_COUNT"] = 1

        self.config["HAS_RTIO_LOG"] = None
        self.config["RTIO_LOG_CHANNEL"] = len(self.rtio_channels)
        self.rtio_channels.append(rtio.LogChannel())

        self.add_rtio(self.rtio_channels)


def main():
    parser = argparse.ArgumentParser(
        description="ARTIQ device binary builder for Shuttler@Genesys2")
    builder_args(parser)
    soc_sdram_args(parser)
    parser.set_defaults(output_dir="artiq_genesys2")
    parser.add_argument("--gateware-identifier-str", default=None,
                        help="Override ROM identifier")
    args = parser.parse_args()

    soc = TestVariant(gateware_identifier_str=args.gateware_identifier_str, **soc_sdram_argdict(args))
    build_artiq_soc(soc, builder_argdict(args))


if __name__ == "__main__":
    main()
