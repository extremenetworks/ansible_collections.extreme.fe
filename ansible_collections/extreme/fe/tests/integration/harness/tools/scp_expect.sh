#!/usr/bin/env expect
# usage: ./scp_expect.sh user host /remote/path /local/path password


# Toggle verbose debugging by setting EXPECT_DEBUG before calling the script.
if {[info exists ::env(EXPECT_DEBUG)] && $::env(EXPECT_DEBUG) ne ""} {
  log_user 1
  exp_internal 1
  exp_internal -f /tmp/expect_trace.log 1
} else {
  log_user 0
  exp_internal 0
}



set timeout 300
set src_file [lindex $argv 0]
set dst_file [lindex $argv 1]
set password [lindex $argv 2]

spawn scp -q ${src_file} ${dst_file}

expect {
  -re {Are you sure you want to continue connecting.*} {
    send "yes\r"
    exp_continue
  }
  -re {.*[Pp]assword:.*} {
    send "$password\r"
    exp_continue
  }
  -re {Permission denied} {
    exit 1
  }
  timeout {
    exit 1
  }
  eof {}
  default {
    exp_continue
  }
}

set wait_result [wait]
set os_error [lindex $wait_result 2]
if {$os_error != 0} {
  exit 1
}
set exit_status [lindex $wait_result 3]
if {$exit_status ne ""} {
  exit $exit_status
}

