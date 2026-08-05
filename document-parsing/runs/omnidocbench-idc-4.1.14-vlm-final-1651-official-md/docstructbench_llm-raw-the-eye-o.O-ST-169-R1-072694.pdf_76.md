## Result Parameter Details

### Peripheral Control Status

The SMPC outputs the peripheral control status to the status register (SR) when the SMPC control mode is used. The status register (SR) is a register that can be read without regard for the INTBACK command. However, when the register is read when the INTBACK command is not in use, all bits except the RESB bit will be undefined.

<table><tr><td>SR</td><td>bit7<br/>1<br/>PDL<br/>NPE<br/>RESB<br/>P2MD1<br/>P2MD0<br/>P1MD1<br/>P1MD0<br/>bit0</td></tr><tr><td>P1MD:</td><td>Port 1 Mode<br/>00: 15-byte mode (Returns peripheral data up to a maximum of 15 bytes.)<br/>01: 255-byte mode (Returns peripheral data up to a maximum of 255 bytes.)<br/>10: Unused<br/>11: 0-byte mode (Port is not accessed.)</td></tr><tr><td>P2MD:</td><td>Port 2 Mode<br/>00: 15-byte mode (Returns peripheral data up to a maximum of 15 bytes.)<br/>01: 255-byte mode (Returns peripheral data up to a maximum of 255 bytes.)<br/>10: Unused<br/>11: 0-byte mode (Port is not accessed.)</td></tr><tr><td>RESB:</td><td>Reset Button Status Bit<br/>0: Reset Button OFF<br/>1: Reset Button ON<br/>Reading without regard for INTBACK command is possible. (Shows status for each V-BLANK-IN.)</td></tr><tr><td>NPE:</td><td>Remaining Peripheral Existence Bit<br/>0: No remaining data<br/>1: Remaining data</td></tr><tr><td>PDL:</td><td>Peripheral Data Location Bit<br/>0: 2nd or above peripheral data<br/>1: 1st peripheral data</td></tr><tr><td>bit7:</td><td>Always 1</td></tr></table>

  Figure 3.13 Peripheral Control Status
