from signal import signal
from migen.build.generic_platform import *
from artiq.gateware import rtio
from migen.genlib.io import DifferentialInput, DDROutput
from artiq.gateware.rtio import rtlink


from migen import *
from numpy import sign


class ShuttlerSamples(Module):

    def __init__(self, target, fmc, dac_awg_reset):

        dac_data_width  = 14
        addr_extension = 2
        enable_extension = 1
        rtlink_data_width = dac_data_width + addr_extension + enable_extension
        # data_addr_offset = dac_data_width
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

        # self.sync.rio_phy += [
        #     If(self.rtlink.o.stb,
                
        #         samples[self.rtlink.o.address].eq(
        #             self.rtlink.o.data[:-1]),
        #         signal_enable.eq(self.rtlink.o.data[-1])
        #     ),
        # ]

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
