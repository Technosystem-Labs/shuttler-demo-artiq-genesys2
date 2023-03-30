from numpy import int32, int64

from artiq.language.core import delay_mu, kernel, delay, portable, at_mu, now_mu
from artiq.language.units import us, ms, ns
from artiq.language.types import TInt32, TFloat, TBool, TList
from artiq.coredevice.rtio import rtio_output

from artiq.coredevice import spi2 as spi


SPI_CONFIG = (0 * spi.SPI_OFFLINE | 0 * spi.SPI_END |
              0 * spi.SPI_INPUT | 0 * spi.SPI_CS_POLARITY |
              1 * spi.SPI_CLK_POLARITY | 1 * spi.SPI_CLK_PHASE |
              0 * spi.SPI_LSB_FIRST | 0 * spi.SPI_HALF_DUPLEX)

# SPI clock write and read dividers
SPIT_CFG_WR = 16
SPIT_CFG_RD = 16

class Shuttler:

    dac_csn_mask = [
        0b1111,
        0b1110,
        0b1101,
        0b1100,
        0b1011,
        0b1010,
        0b1001,
        0b1000
    ]

    kernel_invariants = {"bus", "channel", "core", "dac_csn_mask"}

    def __init__(self, 
                 dmgr, 
                 channel,
                 spi_device, 
                 dac_reset_device, 
                 osc_en_device,
                 mmcx_sel_device,
                 refclk_sel_device,
                 core_device="core"):
        self.core = dmgr.get(core_device)
        self.bus = dmgr.get(spi_device)
        self.channel = channel << 8
        self.dac_reset = dmgr.get(dac_reset_device)
        self.osc_en = dmgr.get(osc_en_device)
        self.mmcx_sel = dmgr.get(mmcx_sel_device)
        self.refclk_sel = dmgr.get(refclk_sel_device)
        self.ref_period_mu = self.core.seconds_to_mu(
            self.core.coarse_ref_period)


    @kernel
    def write(self, addr, value, enable=False):
        # RLINK LAYOUT:
        #   RTLINK ADDRESS -> 8 bits
        #   RTLINK DATA -> 17 bits
        #   
        #   |   RTLINK ADDRESS [7:0]    |
        #   |  ADDR [7:0] (addr & 0xFF) |
        # 
        #   |    RTLINK DATA [16:15]    |   RTLINK DATA[14]     |   RTLINK DATA [13:0]  |
        #   |       ADDR [9:7]          |    Signal Enable      |           value       |

        SE = 1 << 14

        value |= SE

        DAC_WIDTH = 14
        
        value &= (1 << DAC_WIDTH + 1) - 1
        value |= (addr >> 8) << (DAC_WIDTH + 1)
        addr = addr & 0xFF
        
        
        rtio_output(self.channel | addr, value)


    @kernel
    def set_enable(self, enable):
        self.write(0, 0, True)
    
    
    @kernel
    def write_sample(self, n_sample, value):
        self.write(n_sample, value)
        
    
    @kernel
    def write_samples(self, data: TList(TInt32)):
        for i in range (len(data)):
            self.write(i, data[i])
            delay_mu(100*self.ref_period_mu)

    @kernel
    def dac_write(self, dac: TInt32, adr: TInt32, dat: TInt32):
        dac_mask = self.dac_csn_mask[dac]

        self.bus.set_config_mu(SPI_CONFIG | spi.SPI_END, 16,
                               SPIT_CFG_WR, dac_mask)
        cmd = 0b0 << 7 | 0b00 << 5 | adr
        self.bus.write(cmd << 24 | dat << 16)

    @kernel
    def dac_read(self, dac: TInt32, adr: TInt32):
        dac_mask = self.dac_csn_mask[dac]

        self.bus.set_config_mu(SPI_CONFIG, 8,
                               SPIT_CFG_WR, 1 << 3 | dac_mask)
        cmd = 0b1 << 7 | 0b00 << 5 | adr
        self.bus.write(cmd << 24)

        self.bus.set_config_mu(SPI_CONFIG | spi.SPI_END | spi.SPI_INPUT | spi.SPI_HALF_DUPLEX, 8,
                               SPIT_CFG_WR, dac_mask)
        self.bus.write(cmd << 24)
        return self.bus.read()

    @kernel
    def reset_dac(self):
        self.dac_reset.on()
        delay(100*ns)
        self.dac_reset.off()

    @kernel
    def init(self):
        self.reset_dac()
        delay(100*ns)

        # Check communication with DACs and enable on-chip IR_CML and QR_CML
        for i in range(8):
            assert self.dac_read(i, 0x1F) == 0x0A
            delay(10*us)
            self.dac_write(i, 0x5, 1 << 7)
            self.dac_write(i, 0x8, 1 << 7)

        self.osc_en.on()
        self.mmcx_sel.on()
        self.refclk_sel.on()        

    @kernel
    def get_dac_timing_status(self, dac):
        return self.dac_read(dac, 0x14)

    @kernel
    def setup_dac(self, dac):
        self.dac_write(0b1111, 0x7F, 0x81)
            