BLUEZ_PATH=./bluez-5.87

BLUEZ_SRCS  = lib/bluetooth/bluetooth.c lib/bluetooth/hci.c lib/bluetooth/sdp.c lib/bluetooth/uuid.c
BLUEZ_SRCS += attrib/att.c attrib/gatt.c attrib/gattrib.c attrib/utils.c
BLUEZ_SRCS += btio/btio.c src/log.c src/shared/log.c src/shared/mgmt.c
BLUEZ_SRCS += src/shared/crypto.c src/shared/att.c src/shared/queue.c src/shared/util.c
BLUEZ_SRCS += src/shared/io-glib.c src/shared/timeout-glib.c
BLUEZ_SRCS += src/shared/gatt-client.c src/shared/gatt-db.c src/shared/gatt-helpers.c

IMPORT_SRCS = $(addprefix $(BLUEZ_PATH)/, $(BLUEZ_SRCS))
LOCAL_SRCS  = bluepy-helper.c

CC ?= gcc
CFLAGS += -g -Wall # -Werror

CPPFLAGS += -DHAVE_CONFIG_H
ifneq ($(DEBUGGING),)
CFLAGS += -DBLUEPY_DEBUG=1 -O0
else
CFLAGS += -Os
endif

CPPFLAGS += -I$(BLUEZ_PATH)/attrib -I$(BLUEZ_PATH) -I$(BLUEZ_PATH)/lib -I$(BLUEZ_PATH)/src -I$(BLUEZ_PATH)/btio

CPPFLAGS += $(shell pkg-config glib-2.0 --cflags)
LDLIBS += $(shell pkg-config glib-2.0 --libs)

all: bluepy-helper

bluepy-helper: $(LOCAL_SRCS) $(IMPORT_SRCS)
	$(CC) -L. $(CFLAGS) $(CPPFLAGS) -o $@ $(LOCAL_SRCS) $(IMPORT_SRCS) $(LDLIBS)

$(IMPORT_SRCS): bluez-src.tgz
	tar xzf $<
	touch $(IMPORT_SRCS)

.PHONY: bluez-tarfile

# Reproducible: same sources give the same bluez-src.tgz
bluez-tarfile:
	(cd ..; tar --sort=name --mtime='1970-01-01 00:00Z' --owner=0 --group=0 --numeric-owner \
	    -cf - $(BLUEZ_PATH) | gzip -n -9 > bluepy/bluez-src.tgz)

GET_SERVICES=get_services.py

uuids.json: $(GET_SERVICES)
	python3 $(GET_SERVICES) > uuids.json

TAGS: *.c $(BLUEZ_PATH)/attrib/*.[ch] $(BLUEZ_PATH)/btio/*.[ch]
	etags $^

# Unit tests for the C code (no Bluetooth hardware needed)
TEST_SRCS = ../tests/test_helper_reports.c

test-helper: $(TEST_SRCS) $(LOCAL_SRCS) $(IMPORT_SRCS)
	$(CC) -L. $(CFLAGS) $(CPPFLAGS) -I. -o $@ $(TEST_SRCS) $(IMPORT_SRCS) $(LDLIBS)

.PHONY: test
test: test-helper
	./test-helper

clean:
	rm -rf *.o bluepy-helper test-helper TAGS $(BLUEZ_PATH)



