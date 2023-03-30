from migen.build.generic_platform import *
# from shuttler_demo.gateware.cores import _fmc_pin
from migen import *

from artiq.gateware.rtio.phy.spi2 import SPIMaster
from artiq.gateware import rtio
from artiq.gateware.rtio.phy import ttl_simple
from artiq.gateware.rtio import rtlink
from migen.genlib.io import DifferentialInput, DDROutput


def _fmc_pin(fmc: str, bank: str, i: int, pol: str):
    bank = bank.upper()
    pol = pol.upper()
    cc_pin_name_tmp = "fmc{fmc}:{bank}{i:02d}_CC_{pol}"
    pin_name_tmp = "fmc{fmc}:{bank}{i:02d}_{pol}"
    cc_pins = {
        "LA": [0, 1, 17, 18],
        "HA": [0, 1, 17],
        "HB": [0, 6, 17],
    }
    if i in cc_pins[bank]:
        return cc_pin_name_tmp.format(fmc=fmc, bank=bank, i=i, pol=pol)
    else:
        return pin_name_tmp.format(fmc=fmc, bank=bank, i=i, pol=pol)


class ShuttlerSamples(Module):

    def __init__(self, target, fmc, dac_awg_reset):

        dac_data_width  = 14
        addr_extension = 2
        enable_extension = 1
        rtlink_data_width = dac_data_width + addr_extension + enable_extension
        address_width   = 8
        # n_samples = 2^11 = 2048
        # n_samples = 2**((rtlink_data_width - dac_data_width - 1) + address_width)
        n_samples = 1024

        # RTLINK DATA:
        # | ENABLE  |   ADDR_LOW_WORD | ACTUAL DAC WORD |
        # |    17   |       16:14      |     13:0        |

        # INTERNAL ADDRESS
        # | RTLINK_ADDR [7:0] | RTLINK_DATA [16:14]

        self.rtlink = rtlink.Interface(
            rtlink.OInterface(
                data_width=rtlink_data_width,
                address_width=address_width,               
                enable_replace=False
            )
        )
        
        internal_address = Signal(10)     
        self.comb += internal_address.eq(
            Cat(self.rtlink.o.address, 
                self.rtlink.o.data[dac_data_width+enable_extension:]))

        signal_enable = Signal()
        clk_m2c_pads = target.platform.request(f"fmc{fmc}_clk0_m2c")
        clk_m2c = Signal()
        target.specials += [
            DifferentialInput(clk_m2c_pads.p, clk_m2c_pads.n, clk_m2c),
        ]

        target.clock_domains.cd_dac = cd_dac = ClockDomain()
        target.comb += [
            cd_dac.clk.eq(clk_m2c),
            cd_dac.rst.eq(dac_awg_reset)
        ]
        target.platform.add_period_constraint(clk_m2c_pads.p, 8.0)

        samples = Array([Signal(dac_data_width) for x in range(n_samples)])
        adr_ptr = Signal(max=len(samples))

         
        self.sync.rio_phy += [
            If(self.rtlink.o.stb,
                
                samples[internal_address].eq(
                    self.rtlink.o.data[:dac_data_width]),
                signal_enable.eq(self.rtlink.o.data[dac_data_width])
            ),
        ]

        output = Signal(14)
        led_counter = Signal(25)
        target.comb += target.platform.request("user_led", 2).eq(samples[0][-1])
        target.comb += target.platform.request("user_led", 3).eq(dac_awg_reset)
        target.comb += target.platform.request("user_led", 4).eq(output[-1])
        target.comb += target.platform.request("user_led", 6).eq(signal_enable)
        target.sync.dac += [
            If(~signal_enable,
                output.eq(0)
            ).Else(
                output.eq(samples[adr_ptr]),
                led_counter.eq(led_counter+1),
            ),
            If(~signal_enable,
                adr_ptr.eq(0)
            ).Elif(adr_ptr < len(samples),
                adr_ptr.eq(adr_ptr+1)
            ).Else(
                adr_ptr.eq(0)
            )
        ]

        tp_3 = target.platform.request(f"fmc{fmc}_tp3")
        target.specials += [
            DDROutput(0, 1, tp_3, cd_dac.clk)
        ]

        for dac_id in range(8):
            dac_pads = target.platform.request(f"fmc{fmc}_dac", dac_id)
            target.specials += [
                DDROutput(0, 1, dac_pads.dclkio, cd_dac.clk)
            ]
            for idx, dp in enumerate(dac_pads.data):
                target.specials += [
                    DDROutput(output[idx], output[idx], dp, cd_dac.clk)
                ]


class Shuttler:

    @classmethod
    def io(cls, fmc, iostd):
        return [
            (f"fmc{fmc}_dac_spi", 0,
                Subsignal("clk",  Pins(_fmc_pin(fmc, "HB", 16, "n"))),
                Subsignal("mosi", Pins(_fmc_pin(fmc, "HB", 6, "n"))),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_dac_reset", 0, 
                Pins(_fmc_pin(fmc, "HB", 16, "p")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_cs_a0", 0, 
                Pins(_fmc_pin(fmc, "LA", 31, "p")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_cs_a1", 0, 
                Pins(_fmc_pin(fmc, "HB", 19, "p")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_cs_a2", 0, 
                Pins(_fmc_pin(fmc, "LA", 30, "p")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_cs_n", 0, 
                Pins(_fmc_pin(fmc, "LA", 31, "n")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_led0_g", 0, 
                Pins(_fmc_pin(fmc, "HA", 23, "n")),
                iostd["HA"]["single"]),
            (f"fmc{fmc}_led0_r", 0, 
                Pins(_fmc_pin(fmc, "HA", 23, "p")),
                iostd["HA"]["single"]),
            (f"fmc{fmc}_led1_g", 0, 
                Pins(_fmc_pin(fmc, "LA", 32, "p")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_led1_r", 0, 
                Pins(_fmc_pin(fmc, "HB", 18, "n")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_mmcx_oscn_sel", 0, 
                Pins(_fmc_pin(fmc, "HB", 17, "n")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_refclk_sel", 0, 
                Pins(_fmc_pin(fmc, "LA", 32, "n")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_osc_en", 0, 
                Pins(_fmc_pin(fmc, "HB", 20, "n")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_osc_scl", 0, 
                Pins(_fmc_pin(fmc, "HB", 21, "n")),
               iostd["HB"]["single"]),
            (f"fmc{fmc}_osc_sck", 0, 
                Pins(_fmc_pin(fmc, "HB", 20, "p")),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_tp3", 0, 
                Pins(_fmc_pin(fmc, "LA", 33, "n")),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_dac", 0,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "HA",  6, "n"),
                    _fmc_pin(fmc, "HA",  6, "p"),
                    _fmc_pin(fmc, "HA",  7, "n"),
                    _fmc_pin(fmc, "HA",  2, "n"),
                    _fmc_pin(fmc, "HA",  7, "p"),
                    _fmc_pin(fmc, "HA",  2, "p"),
                    _fmc_pin(fmc, "HA",  3, "n"),
                    _fmc_pin(fmc, "HA",  3, "p"),
                    _fmc_pin(fmc, "HA",  4, "n"),
                    _fmc_pin(fmc, "HA",  4, "p"),
                    _fmc_pin(fmc, "HA",  5, "n"),
                    _fmc_pin(fmc, "HA",  5, "p"),
                    _fmc_pin(fmc, "HA",  0, "n"),
                    _fmc_pin(fmc, "HA",  1, "n"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "HA",  0, "p"))),
                iostd["HA"]["single"]),
            (f"fmc{fmc}_dac", 1,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "LA",  9, "p"),
                    _fmc_pin(fmc, "LA",  9, "n"),
                    _fmc_pin(fmc, "LA",  7, "n"),
                    _fmc_pin(fmc, "LA",  8, "n"),
                    _fmc_pin(fmc, "LA",  7, "p"),
                    _fmc_pin(fmc, "LA",  8, "p"),
                    _fmc_pin(fmc, "LA",  5, "n"),
                    _fmc_pin(fmc, "LA",  4, "n"),
                    _fmc_pin(fmc, "LA",  5, "p"),
                    _fmc_pin(fmc, "LA",  6, "n"),
                    _fmc_pin(fmc, "LA",  4, "p"),
                    _fmc_pin(fmc, "LA",  3, "n"),
                    _fmc_pin(fmc, "LA",  3, "p"),
                    _fmc_pin(fmc, "LA",  6, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "LA", 0, "p"))),
                iostd["LA"]["single"]),
            (f"fmc{fmc}_dac", 2,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "HA", 14, "n"),
                    _fmc_pin(fmc, "HA", 14, "p"),
                    _fmc_pin(fmc, "HA", 12, "n"),
                    _fmc_pin(fmc, "HA", 12, "p"),
                    _fmc_pin(fmc, "HA", 13, "n"),
                    _fmc_pin(fmc, "HA", 10, "n"),
                    _fmc_pin(fmc, "HA", 10, "p"),
                    _fmc_pin(fmc, "HA", 11, "n"),
                    _fmc_pin(fmc, "HA", 11, "p"),
                    _fmc_pin(fmc, "HA", 13, "p"),
                    _fmc_pin(fmc, "HA",  8, "n"),
                    _fmc_pin(fmc, "HA",  8, "p"),
                    _fmc_pin(fmc, "HA",  9, "n"),
                    _fmc_pin(fmc, "HA",  9, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "HA",  1, "p"))),
                iostd["HA"]["single"]),
            (f"fmc{fmc}_dac", 3,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "LA", 14, "n"),
                    _fmc_pin(fmc, "LA", 15, "n"),
                    _fmc_pin(fmc, "LA", 16, "n"),
                    _fmc_pin(fmc, "LA", 15, "p"),
                    _fmc_pin(fmc, "LA", 14, "p"),
                    _fmc_pin(fmc, "LA", 13, "n"),
                    _fmc_pin(fmc, "LA", 16, "p"),
                    _fmc_pin(fmc, "LA", 13, "p"),
                    _fmc_pin(fmc, "LA", 11, "n"),
                    _fmc_pin(fmc, "LA", 12, "n"),
                    _fmc_pin(fmc, "LA", 11, "p"),
                    _fmc_pin(fmc, "LA", 12, "p"),
                    _fmc_pin(fmc, "LA", 10, "n"),
                    _fmc_pin(fmc, "LA", 10, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "LA",  1, "p"))),
                iostd["LA"]["single"]),
            # done
            (f"fmc{fmc}_dac", 4,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "HA", 22, "n"),
                    _fmc_pin(fmc, "HA", 19, "n"),
                    _fmc_pin(fmc, "HA", 22, "p"),
                    _fmc_pin(fmc, "HA", 21, "n"),
                    _fmc_pin(fmc, "HA", 21, "p"),
                    _fmc_pin(fmc, "HA", 19, "p"),
                    _fmc_pin(fmc, "HA", 18, "n"),
                    _fmc_pin(fmc, "HA", 20, "n"),
                    _fmc_pin(fmc, "HA", 20, "p"),
                    _fmc_pin(fmc, "HA", 18, "p"),
                    _fmc_pin(fmc, "HA", 15, "n"),
                    _fmc_pin(fmc, "HA", 15, "p"),
                    _fmc_pin(fmc, "HA", 16, "n"),
                    _fmc_pin(fmc, "HA", 16, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "HA", 17, "p"))),
                iostd["HA"]["single"]),
            # done
            (f"fmc{fmc}_dac", 5,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "LA", 24, "n"),
                    _fmc_pin(fmc, "LA", 25, "n"),
                    _fmc_pin(fmc, "LA", 24, "p"),
                    _fmc_pin(fmc, "LA", 25, "p"),
                    _fmc_pin(fmc, "LA", 21, "n"),
                    _fmc_pin(fmc, "LA", 21, "p"),
                    _fmc_pin(fmc, "LA", 22, "n"),
                    _fmc_pin(fmc, "LA", 22, "p"),
                    _fmc_pin(fmc, "LA", 23, "n"),
                    _fmc_pin(fmc, "LA", 23, "p"),
                    _fmc_pin(fmc, "LA", 19, "n"),
                    _fmc_pin(fmc, "LA", 19, "p"),
                    _fmc_pin(fmc, "LA", 20, "n"),
                    _fmc_pin(fmc, "LA", 20, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "LA", 17, "p"))),
                iostd["LA"]["single"]),
            # done
            (f"fmc{fmc}_dac", 6,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "HB", 8, "n"),
                    _fmc_pin(fmc, "HB", 8, "p"),
                    _fmc_pin(fmc, "HB", 7, "n"),
                    _fmc_pin(fmc, "HB", 7, "p"),
                    _fmc_pin(fmc, "HB", 4, "n"),
                    _fmc_pin(fmc, "HB", 4, "p"),
                    _fmc_pin(fmc, "HB", 1, "n"),
                    _fmc_pin(fmc, "HB", 5, "n"),
                    _fmc_pin(fmc, "HB", 1, "p"),
                    _fmc_pin(fmc, "HB", 5, "p"),
                    _fmc_pin(fmc, "HB", 2, "n"),
                    _fmc_pin(fmc, "HB", 2, "p"),
                    _fmc_pin(fmc, "HB", 3, "n"),
                    _fmc_pin(fmc, "HB", 3, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "HB", 0, "p"))),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_dac", 7,
                Subsignal("data", Pins(
                    _fmc_pin(fmc, "HB", 13, "n"),
                    _fmc_pin(fmc, "HB", 12, "n"),
                    _fmc_pin(fmc, "HB", 13, "p"),
                    _fmc_pin(fmc, "HB", 12, "p"),
                    _fmc_pin(fmc, "HB", 15, "n"),
                    _fmc_pin(fmc, "HB", 15, "p"),
                    _fmc_pin(fmc, "HB", 11, "n"),
                    _fmc_pin(fmc, "HB",  9, "n"),
                    _fmc_pin(fmc, "HB",  9, "p"),
                    _fmc_pin(fmc, "HB", 14, "n"),
                    _fmc_pin(fmc, "HB", 14, "p"),
                    _fmc_pin(fmc, "HB", 10, "n"),
                    _fmc_pin(fmc, "HB", 10, "p"),
                    _fmc_pin(fmc, "HB", 11, "p"))),
                Subsignal("dclkio", Pins(_fmc_pin(fmc, "HB",  6, "p"))),
                iostd["HB"]["single"]),
            (f"fmc{fmc}_osc_i2c", 0,
                Subsignal("scl", Pins(_fmc_pin(fmc, "HB", 21, "n"))),
                Subsignal("sda", Pins(_fmc_pin(fmc, "HB", 20, "p"))),
                iostd["HB"]["single"]
            ),
        ]

    @classmethod
    def add_std(cls, target, fmc, iostd):
        target.platform.add_extension(cls.io(fmc, iostd))

        # SPI
        dac_spi = target.platform.request(f"fmc{fmc}_dac_spi")
        dac_spi.cs_n = Signal(4)
        target.comb += Cat(
            *[target.platform.request(f"fmc{fmc}_cs_a{i}") for i in range(3)],
            target.platform.request(f"fmc{fmc}_cs_n")
        ).eq(dac_spi.cs_n)

        # ch. 0
        phy = SPIMaster(dac_spi)
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy, ififo_depth=4))

        # ch. 1
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_led0_g"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 2
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_led0_r"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 3
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_led1_g"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 4
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_led1_r"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 5
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_mmcx_oscn_sel"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 6
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_refclk_sel"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 7
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_osc_en"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 8
        phy = ttl_simple.Output(target.platform.request(f"fmc{fmc}_dac_reset"))
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # DAC Testing

        # ch. 9
        dac_awg_reset = Signal()
        phy = ttl_simple.Output(dac_awg_reset)
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))

        # ch. 10
        phy = ShuttlerSamples(target, fmc, dac_awg_reset)
        target.submodules += phy
        target.rtio_channels.append(rtio.Channel.from_phy(phy))
