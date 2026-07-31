## Dispatch list format

Although the Dispatch API provides functions for parsing and accessing the dispatch result, you may want to handle the response yourself. In that case, this description of the returned dispatch list may be helpful.

Designed for ZLink IoT Cloud (version 3.2+), enables gateways and edge devices to exchange batch control or data acquisition tasks using a compact and extensible TLV (Type-Length-Value) binary encoding. This approach ensures compatibility across vendors #rows, supports dynamic task type extensions, and performs reliably even under constrained network conditions. The following sections outline the technical specification and usage guidelines for this fictional API.Also, note that there is one key, #ISS_SLIS_DIAGS, which does not confirmed.

## Tag descriptions

The following table provides description for the tages used in a dispatch query result:

Tag Description

#headers Pre-defined headers for the dispatch list.

#columns The column heading names for the list.

#widths The widths for each column, used in formatting the data.

#types The data types for each column. Normally used to decide how to justify a column by default.

#lotcol Which column contains the lot names.

#rows The query data table in row-major form.

#blocked A flag for each lot that indicates if it is blocked. The WorkStram dispatcher interface uses this flag to determine whether that lot is selectable by the operator.
















<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Tag</td><td style='text-align: center; word-wrap: break-word;'>Description</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#headers</td><td style='text-align: center; word-wrap: break-word;'>Pre-defined headers for the dispatch list.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#columns</td><td style='text-align: center; word-wrap: break-word;'>The column heading names for the list.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#widths</td><td style='text-align: center; word-wrap: break-word;'>The widths for each column, used in formatting the data.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#types</td><td style='text-align: center; word-wrap: break-word;'>The data types for each column. Normally used to decide how to justify a column by default.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#lotcol</td><td style='text-align: center; word-wrap: break-word;'>Which column contains the lot names.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#rows</td><td style='text-align: center; word-wrap: break-word;'>The query data table in row-major form.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#blocked</td><td style='text-align: center; word-wrap: break-word;'>A flag for each lot that indicates if it is blocked. The WorkStram dispatcher interface uses this flag to determine whether that lot is selectable by the operator.</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>#ISS-DDIS-DIAGS</td><td style='text-align: center; word-wrap: break-word;'>This is diagnostic information from the dispatcher, relating to the execution time of the rule. Note that it does not follow the same “#tag value” formats as the other tags.</td></tr></table>

#ISS-DDIS-

DIAGS

This is diagnostic information from the dispatcher, relating to the execution time of the rule. Note that it does not follow the same “#tag value” formats as the other tags.

## Parding the dispatch list

The following functions are available for parding and processing the dispatcher result:

[C++]

#include "writerlibx/iss_schedmsg.h"

#include "writerlibx/iss_schedmsg_print.h"

/* Parsing of raw dispatch results */

schedmsg * iss_parseSchedMsg(const char *rawText, u_int text Size);