/*
 * Tests for the advertising report parsing in bluepy-helper.c
 *
 * Build and run with:
 *     $ make -C bluepy test
 */

#define main bluepy_helper_main
#include "bluepy-helper.c"
#undef main

static int failures;

/* Runs fn(data, len) with stdout captured, and compares the output */
static void check(const char *name, void (*fn)(const uint8_t *, size_t),
                  const uint8_t *data, size_t len, const char *expected)
{
    char *out = NULL;
    size_t out_len = 0;
    FILE *saved = stdout;
    FILE *mem = open_memstream(&out, &out_len);

    stdout = mem;
    fn(data, len);
    fflush(mem);
    stdout = saved;
    fclose(mem);

    if (strcmp(out, expected)) {
        failures++;
        fprintf(stderr, "FAIL: %s\n  expected: %s\n  got:      %s\n", name, expected, out);
    } else {
        fprintf(stderr, "ok:   %s\n", name);
    }
    free(out);
}

#define SCAN "rsp=$scan" RESP_DELIM
#define D RESP_DELIM

/* Extended report header: evt_type, addr_type, addr (AA:BB:CC:DD:EE:F<last>),
 * sid, rssi -60, data_len */
#define EXT_REPORT(evt_type, addr_type, last, sid, data_len) \
    (evt_type) & 0xFF, (evt_type) >> 8, (addr_type), \
    (last), 0xEE, 0xDD, 0xCC, 0xBB, 0xAA, \
    0x01, 0x00, (sid), 0x7F, 0xC4, 0x00, 0x00, 0x00, \
    0, 0, 0, 0, 0, 0, (data_len)

int main(void)
{
    conn_state = STATE_SCANNING;

    {
        /* Two reports in one event: ADV_IND from a public address,
         * ADV_NONCONN_IND from a random one, with data */
        const uint8_t ev[] = { 2,
            0x00, 0x00, 0xFF, 0xEE, 0xDD, 0xCC, 0xBB, 0xAA, 0, 0xC4,
            0x03, 0x01, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 3, 0x02, 0x01, 0x06, 0xB0 };
        check("legacy, two reports", process_adv_report, ev, sizeof(ev),
              SCAN "addr=bAABBCCDDEEFF" D "type=h1" D "rssi=h3C" D "flag=h0\n"
              SCAN "addr=b060504030201" D "type=h2" D "rssi=h50" D "flag=h4" D "d=b020106\n");

        check("legacy, truncated", process_adv_report, ev, sizeof(ev) - 2,
              SCAN "addr=bAABBCCDDEEFF" D "type=h1" D "rssi=h3C" D "flag=h0\n");
    }
    {
        /* Bluetooth 5 controller reporting a legacy connectable PDU */
        const uint8_t ev[] = { 1, EXT_REPORT(0x0013, 0x00, 0xFF, 0xFF, 3), 0x02, 0x01, 0x06 };
        check("extended, complete", process_ext_adv_report, ev, sizeof(ev),
              SCAN "addr=bAABBCCDDEEFF" D "type=h1" D "rssi=h3C" D "flag=h0" D "d=b020106\n");
    }
    {
        /* Identity address resolved by the controller, not connectable */
        const uint8_t ev[] = { 1, EXT_REPORT(0x0000, 0x03, 0xF0, 1, 0) };
        check("extended, identity address", process_ext_adv_report, ev, sizeof(ev),
              SCAN "addr=bAABBCCDDEEF0" D "type=h2" D "rssi=h3C" D "flag=h4\n");
    }
    {
        /* Anonymous advertising has no address: it must not show up as
         * 00:00:00:00:00:00 */
        const uint8_t ev[] = { 1, EXT_REPORT(0x0000, 0xFF, 0x00, 1, 1), 0x00 };
        check("extended, anonymous ignored", process_ext_adv_report, ev, sizeof(ev), "");
    }
    {
        /* Data split in two reports: "more data" (bit 5), then complete */
        const uint8_t ev[] = { 2,
            EXT_REPORT(0x0021, 0x01, 0xF1, 2, 2), 0x02, 0x01,
            EXT_REPORT(0x0001, 0x01, 0xF1, 2, 1), 0x06 };
        check("extended, fragments joined", process_ext_adv_report, ev, sizeof(ev),
              SCAN "addr=bAABBCCDDEEF1" D "type=h2" D "rssi=h3C" D "flag=h0" D "d=b020106\n");
    }
    {
        /* A fragment whose continuation never comes is still reported */
        const uint8_t ev[] = { 2,
            EXT_REPORT(0x0021, 0x01, 0xF1, 2, 1), 0xAB,
            EXT_REPORT(0x0001, 0x00, 0xF2, 3, 1), 0xCD };
        check("extended, unfinished fragment flushed", process_ext_adv_report, ev, sizeof(ev),
              SCAN "addr=bAABBCCDDEEF1" D "type=h2" D "rssi=h3C" D "flag=h0" D "d=bAB\n"
              SCAN "addr=bAABBCCDDEEF2" D "type=h1" D "rssi=h3C" D "flag=h0" D "d=bCD\n");
    }
    {
        /* Data length beyond the end of the event */
        const uint8_t ev[] = { 1, EXT_REPORT(0x0001, 0x00, 0xF3, 1, 200), 0x01 };
        check("extended, truncated", process_ext_adv_report, ev, sizeof(ev), "");
    }
    {
        /* More fragments than the reassembly buffer holds */
        uint8_t ev[1 + 7 * (EXT_ADV_REPORT_FIXED_SIZE + 255)];
        uint8_t *p = ev + 1;
        int i;

        ev[0] = 7;
        for (i = 0; i < 7; i++) {
            const uint8_t hdr[] = { EXT_REPORT(i < 6 ? 0x0021 : 0x0001, 0x00, 0xF4, 1, 255) };
            memcpy(p, hdr, sizeof(hdr));
            memset(p + sizeof(hdr), 0x11, 255);
            p += sizeof(hdr) + 255;
        }
        {
            char expected[200 + 2 * EXT_ADV_MAX_DATA];
            char *e = expected + sprintf(expected, SCAN "addr=bAABBCCDDEEF4" D "type=h1" D
                                         "rssi=h3C" D "flag=h0" D "d=b");
            for (i = 0; i < EXT_ADV_MAX_DATA; i++)
                e += sprintf(e, "11");
            strcpy(e, "\n");
            check("extended, oversized data clamped", process_ext_adv_report, ev, sizeof(ev),
                  expected);
        }
    }

    conn_state = STATE_DISCONNECTED;
    {
        const uint8_t ev[] = { 1, EXT_REPORT(0x0001, 0x00, 0xF5, 1, 0) };
        check("not scanning, nothing reported", process_ext_adv_report, ev, sizeof(ev), "");
    }

    if (failures)
        fprintf(stderr, "%d test(s) failed\n", failures);
    return failures ? 1 : 0;
}
