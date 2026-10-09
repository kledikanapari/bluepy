async function switchViewFromModelID(model, sku) {
    localStorage.setItem("model", JSON.stringify(model));
    localStorage.setItem("sku", sku);
    if (sku === null || sku === "") {
        document.getElementById("scan_button-c").innerText = "Incompatible Device";
        return;
    }
    console.log("Switching view from model ID " + model.base);
    if (model.base == "B181") {
        window.location.href = "MainControl_one";
    } else if (model.base == "B157") {
        window.location.href = "MainControl_sticks";
    } else if (model.base == "B155") {
        window.location.href = "MainControl_two";
    } else if (model.base == "B163") {
        window.location.href = "MainControl_corsola";
    } else if (model.base == "B171") {
        window.location.href = "MainControl_twos";
    } else if (model.base == "B172" || model.base == "B195") {
        window.location.href = "MainControl_espeon";
    } else if (model.base == "B168") {
        window.location.href = "MainControl_donphan";
    } else if (model.base == "B174") {
        window.location.href = "MainControl_flaaffy";
    } else if (model.base == "B162") {
        window.location.href = "MainControl_cleffa";
    } else if (model.base == "B184") {
        window.location.href = "MainControl_gligar";
    } else if (model.base == "B179" || model.base == "B197") {
        window.location.href = "MainControl_girafarig";
    } else if (model.base == "B185") {
        window.location.href = "MainControl_hoothoot";
    } else if (model.base == "B170") {
        window.location.href = "MainControl_elekid";
    } else if (model.base == "B164") {
        window.location.href = "MainControl_crobat";
    } else if (model.base == "B175") {
        window.location.href = "MainControl_forretress";
    } else if (model.base == "B173") {
        window.location.href = "MainControl_feraligator";
    } else if (model.base == "B189") {
        window.location.href = "MainControl_igglybuff";
    } else if (model.base == "B186") {
        window.location.href = "MainControl_hoppip";
    } else if (model.base == "B190") {
        window.location.href = "MainControl_jumpluff";
    } else if (model.base == "B192") {
        window.location.href = "MainControl_lanturn";
    } else {
        document.getElementById("scan_button-c").innerText = "Incompatible Device";
    }
}
async function scanNewDevices() {
    document.getElementById("device_container").innerHTML = '<img src="../assets/loading.svg" alt="loading_animation" class="h-[80px] w-[80px] m-auto" id="loading_animation" />';
    document.getElementById("scan_button").style.display = "none";
    const SPP_UUID = "aeac4a03-dff5-498f-843a-34487cf133eb";
    const FASTPAIR_UUID = "df21fe2c-2515-4fdb-8886-f12c4d67927c";
    sppPort = await navigator.serial.requestPort({
        allowedBluetoothServiceClassIds: [FASTPAIR_UUID],
        filters: [{ bluetoothServiceClassId: FASTPAIR_UUID }],
    });

    if (sppPort) {
        console.log('connected to a Bluetooth Serial Port Profile port', sppPort.getInfo());
        //print mac address of the connected device
        console.log(sppPort);
        await sppPort.open({ baudRate: 9600 });
        //read from the serial port
        const reader = sppPort.readable.getReader();
        while (true) {
            const { value, done } = await reader.read();
            //console.log(value);
            //print hex string of the received data
            var string = "";
            for (let i = 0; i < value.length; i++) {
                //fill the string with leading zero if needed
                string += (value[i] < 16 ? "0" : "") + value[i].toString(16);
            }
            console.log(string);
            if (done) {
                // Allow the serial port to be closed later.
                reader.releaseLock();
                break;
            }
            console.log(value);
            //if received data is 7 bytes long, disconnect
            if (value.length > 1) {
                reader.releaseLock();
                await sppPort.close();
                var modelID = string.substring(8, 14);
                console.log(modelID);
                switchViewFromModelID(modelID);
                break;
            }
        }
    }
    setTimeout(function(){
        window.location.reload();
    }, 3000);
}
// Fast Pair message stream: group (1) | code (1) | length (2, big endian) | data.
// The model ID is sent as group 0x03 (device information), code 0x01, 3 bytes of data.
function findFastpairModelID(buffer) {
	let offset = 0;
	while (buffer.length - offset >= 4) {
		let group = buffer[offset];
		let code = buffer[offset + 1];
		let length = (buffer[offset + 2] << 8) | buffer[offset + 3];
		if (buffer.length - offset < 4 + length) {
			break;
		}
		if (group === 0x03 && code === 0x01 && length === 3) {
			let modelID = "";
			for (let i = 0; i < 3; i++) {
				modelID += buffer[offset + 4 + i].toString(16).padStart(2, "0");
			}
			return modelID.toUpperCase();
		}
		offset += 4 + length;
	}
	return null;
}

async function scanNewDevicesFastpair() {
	const SPP_UUID = "aeac4a03-dff5-498f-843a-34487cf133eb";
	const FASTPAIR_UUID = "df21fe2c-2515-4fdb-8886-f12c4d67927c";
	try {
		await forgetAllDevices();
	} catch (error) {
		console.error('Failed to forget previous devices', error);
	}
	try {
		sppPort = await navigator.serial.requestPort({
			allowedBluetoothServiceClassIds: [SPP_UUID, FASTPAIR_UUID],
			filters: [{ bluetoothServiceClassId: FASTPAIR_UUID }],
		});
	}
	catch (error) {
		console.error('Connection failed', error);
		document.getElementById("scan_button-c").innerText = "Device not selected";
		setTimeout(function () {
			window.location.reload();
		}, 3000);
		return;
	}

	if (sppPort) {
		console.log('connected to a Bluetooth Serial Port Profile port, waiting for id data...', sppPort.getInfo());
		console.log(sppPort);
		try {
			await sppPort.open({ baudRate: 9600 });
		} catch (error) {
			console.error('Failed to open port', error);
			document.getElementById("scan_button-c").innerText = "Connection failed, retry";
			return;
		}
		document.getElementById("scan_button-c").innerText = "Connecting...";
		//read from the serial port
		const reader = sppPort.readable.getReader();
		// Give up if the device never sends its model ID
		const timeout = setTimeout(function () {
			reader.cancel().catch(function () { });
		}, 15000);
		let received = new Uint8Array(0);
		let modelID = null;
		try {
			while (true) {
				const { value, done } = await reader.read();
				if (done) {
					break;
				}
				// The id message can be split across reads or merged with other messages
				let merged = new Uint8Array(received.length + value.length);
				merged.set(received);
				merged.set(value, received.length);
				received = merged;
				modelID = findFastpairModelID(received);
				if (modelID) {
					console.log("Received id data: " + modelID);
					break;
				}
			}
		} catch (error) {
			console.error('Failed to read device id', error);
		} finally {
			clearTimeout(timeout);
			reader.releaseLock();
			try {
				await sppPort.close();
			} catch (error) {
				console.error('Failed to close port', error);
			}
		}
		if (!modelID) {
			document.getElementById("scan_button-c").innerText = "No response, retry";
			return;
		}
		var modelInfo = getModelFromFastpair(modelID);
		if (modelInfo) {
			switchViewFromModelID(modelInfo, modelID);
		}
		else {
			document.getElementById("scan_button-c").innerText = "Incompatible Device";
		}
	}
}
