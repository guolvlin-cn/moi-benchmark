# **Dispatch list format**

Although the Dispatch API provides functions for parsing and accessing the dispatch result, you may want to handle the response yourself. In that case, this description of the returned dispatch list may be helpful.​Pre-defined headers for the dispatch list

Designed for ZLink IoT Cloud (version 3.2+), enables gateways and edge devices to exchange batch control or data acquisition tasks using a compact and extensible TLV (Type–Length–Value)​ binary encoding. This approach ensures compatibility across vendors #rows, supports dynamic task type extensions, and performs reliably even under constrained network conditions. The following sections outline the technical specification and usage guidelines for this fictional API.Also, note that there is one key, #ISS\_SLIS\_DIAGS, which does not confirmed.

# **Tag descriptions**

The following table provides description for the tages used in a dispatch query result:

**Tag	Description**

#headers	Pre-defined headers for the dispatch list.

#columns	The column heading names for the list.

#widths	The widths for each column, used in formating the data.

#types	The data types for each column. Normally used to decide how to justify a column by default.

#lotcol	Which column contains the lot names.

#rows	The query data table in row-major form.

#blocked	A flag for each lot that indicates if it is blocked. The WorkStram dispatcher interface uses this flag to determine whether that lot is selectable by the operator.

#ISS-DDIS-	This is diagnostic information from the dispatcher, relating

DIAGS      	to the execution time of the rule. Note that it does not follow 		the same “#tag value” formats as the otheer tags.

# **Parding the dispatch list**

The following functions are available for parding and processing the dispatcher result:

[C++]

#include “writerlibx/iss\_schedmsg.h”

#include “writerlibx/iss\_schedmsg\_print.h”

/\* Parsing of raw dispatch results \*/

schedmsg \* iss\_parseSchedMsg(const char \*rawText, u\_int text Size);