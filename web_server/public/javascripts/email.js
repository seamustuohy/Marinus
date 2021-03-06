"use strict";

/**
 * Copyright 2018 Adobe. All rights reserved.
 * This file is licensed to you under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License. You may obtain a copy
 * of the License at http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed under
 * the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR REPRESENTATIONS
 * OF ANY KIND, either express or implied. See the License for the specific language
 * governing permissions and limitations under the License.
 */

window.addEventListener("load", buildPage);

function buildPage() {
    get_lists("mx");
    get_lists("spf");
    get_lists("dkim");
}

function get_lists(reqType) {
    let url;
    if (reqType === "mx") {
	   url = "/api/v1.0/dns?dnsType=mx&list=1";
    } else if (reqType === "spf") {
       url = "/api/v1.0/dns?txtSearch=spf&list=1";
    } else {
       url = "/api/v1.0/dns?txtSearch=dkim&list=1";
    }

    make_get_request(url, displayMetaResults, reqType);
}

function displayMetaResults(results, reqType) {
    var htmlOut = "";
    htmlOut += '\
<coral-columnview class="guide-columnview-example" id="' + reqType + 'Col">\
  <coral-columnview-column>\
    <coral-columnview-column-content>';
    for (var i=0; i< results.length; i++) {
        htmlOut  += '<coral-columnview-item variant="drilldown" icon="file" id="' + reqType + 'Tbl:' + results[i]['_id'] + '">' + results[i]['_id'] + ' (' + results[i]['count'].toString() + ')' + '</coral-columnview-item>';
    }
    htmlOut += '</coral-columnview-column-content>\
  </coral-columnview-column>\
</coral-columnview><br/>';
    var mxTable = document.getElementById(reqType + "Table");
    mxTable.innerHTML = htmlOut;
    document.getElementById(reqType + "Col").on("coral-columnview:activeitemchange", update_div_preview);
}

function update_preview(obj, reqSource) {
    var preview;
    if (reqSource.includes("mx")) {
        preview = document.getElementById("mxResult");
    } else if (reqSource.includes("spf")) {
        preview = document.getElementById("spfResult");
    } else {
        preview = document.getElementById("dkimResult");
    }

    var outputHTML = create_new_table();
    outputHTML += create_table_head(["Zone", "Domain", "Value"]);
    outputHTML += create_table_body();

    for (var i=0; i<obj.length; i++) {
        outputHTML += create_table_row();
        outputHTML += create_table_entry(create_anchor("/zone?search=" + obj[i]['zone'], obj[i]['zone']));
        outputHTML += create_table_entry(create_anchor("/domain?search=" + obj[i]['fqdn'], obj[i]['fqdn']));
        outputHTML += create_table_entry(obj[i]['value']);
        outputHTML += end_table_row();
    }

    outputHTML += end_table();
    preview.innerHTML = outputHTML;
}

function update_div_preview(ev) {
    if (ev == null || ev.detail == null) {
        return false;
    }
    var id = ev.detail.activeItem.id;
    var parts = id.split(/:/);
    var zone = parts[1];

    let url;
    if (parts[0].includes("mx")) {
        url = "/api/v1.0/dns?dnsType=mx&zone=" + zone;
    } else if (parts[0].includes("spf")) {
        url = "/api/v1.0/dns?txtSearch=spf&zone=" + zone;
    } else {
        url = "/api/v1.0/dns?txtSearch=dkim&zone=" + zone;
    }

    make_get_request(url, update_preview, parts[0]);
}
