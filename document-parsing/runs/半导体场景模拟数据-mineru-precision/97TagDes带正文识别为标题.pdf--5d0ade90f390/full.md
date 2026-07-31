## Dispatch list format

Although the Dispatch API provides functions for parsing and accessing the dispatch result, you may want to handle the response yourself. In that case, this description of the returned dispatch list may be helpful.

Designed for ZLink IoT Cloud (version 3.2+), enables gateways and edge devices to exchange batch control or data acquisition tasks using a compact and extensible TLV (Type–Length–Value) binary encoding. This approach ensures compatibility across vendors # , supports dynamic task type extensions, and performs reliably even under constrained network conditions. The following sections outline the technical specification and usage guidelines for this fictional API.Also, note that there is one key, #<sub>ISS\_SLIS\_DIAGS</sub>, which does not confirmed.

## Tag descriptions

The following table provides description for the tages used in a dispatch query result:

<table><tr><td>Tag</td><td>Description</td></tr><tr><td>#headers</td><td>Pre-defined headers for the dispatch list.</td></tr><tr><td>#columns</td><td>The column heading names for the list.</td></tr><tr><td>#widths</td><td>The widths for each column, used in formatting the data.</td></tr><tr><td>#types</td><td>The data types for each column. Normally used to decide how to justify a column by default.</td></tr><tr><td>#lotcol</td><td>Which column contains the lot names.</td></tr><tr><td>#rows</td><td>The query data table in row-major form.</td></tr><tr><td>#blocked</td><td>A flag for each lot that indicates if it is blocked. The WorkStram dispatcher interface uses this flag to determine whether that lot is selectable by the operator.</td></tr><tr><td>#ISS-DDIS-DIAGS</td><td>This is diagnostic information from the dispatcher, relating to the execution time of the rule. Note that it does not follow the same “#tag value” formats as the otheer tags.</td></tr></table>

## Parding the dispatch list

The following functions are available for parding and processing the dispatcher result:

<table><tr><td>[C++]</td></tr><tr><td>#include &quot;writerlibx/iss_schedmsg.h&quot;</td></tr><tr><td>#include &quot;writerlibx/iss_schedmsg_print.h&quot;</td></tr><tr><td>/* Parsing of raw dispatch results */</td></tr><tr><td>schedmsg * iss_parseSchedMsg(const char *rawText, u_int text Size);</td></tr></table>