// Update detection stats + location
async function updateStatus() {
    try {
        const res = await fetch("/status");
        const data = await res.json();

        document.getElementById("status").innerText = data.status;
        document.getElementById("abnormal-detections").innerText = data.abnormal_detections;
        document.getElementById("alerts-count").innerText = data.alerts_count;
        document.getElementById("last-behavior").innerText = data.last_behavior;
        document.getElementById("datetime").innerText = data.datetime;
        document.getElementById("geo-tag").innerText = data.geo_tag;
        document.getElementById("geo-tag-live").innerText = "Location: " + data.geo_tag;
    } catch (err) {
        console.error("Error fetching status:", err);
    }
}

// Update contacts (optional)
async function updateContacts() {
    try {
        const res = await fetch("/contacts");
        const contacts = await res.json();
        const ul = document.getElementById("contacts-list");
        ul.innerHTML = "";
        contacts.forEach(contact => {
            const li = document.createElement("li");
            li.innerText = `${contact.name}: ${contact.phone}`;
            ul.appendChild(li);
        });
    } catch (err) {
        console.error("Error fetching contacts:", err);
    }
}

// Refresh intervals
setInterval(updateStatus, 2000);    // every 2 sec
setInterval(updateContacts, 5000);  // every 5 sec

// Initial fetch
updateStatus();
updateContacts();







