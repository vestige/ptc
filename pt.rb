#!/usr/bin/env ruby
# frozen_string_literal: true

# Console Timer (Ruby)
# - supports seconds
# - shows progress bar with "*" and changing color
# - handles Ctrl+C gracefully
#
# Usage examples:
#   ruby pomotimer.rb 25m
#   ruby pomotimer.rb 90s
#   ruby pomotimer.rb 1m30s
#   ruby pomotimer.rb 1500        # seconds
#   ruby pomotimer.rb 25:00       # mm:ss
#   ruby pomotimer.rb 00:30       # mm:ss

class ConsoleTimer
  BAR_WIDTH_DEFAULT = 50

  def initialize(total_seconds:, label: "TIMER", bar_width: BAR_WIDTH_DEFAULT, tick: 0.01)
    raise ArgumentError, "total_seconds must be >= 1" if total_seconds < 1

    @total = total_seconds
    @label = label
    @bar_width = bar_width
    @tick = tick

    @t0 = nil
    @last_rendered_sec = nil
    @running = false
  end

  def run
    trap_signals

    @t0 = now
    @running = true
    hide_cursor

    loop do
      elapsed = (now - @t0)
      remaining = @total - elapsed
      break if remaining <= 0

      current_sec = elapsed.floor
      if @last_rendered_sec != current_sec
        render(elapsed, remaining)
        @last_rendered_sec = current_sec
      end

      sleep(@tick)
    end

    render(@total, 0.0)
    finish_message
  ensure
    show_cursor
    @running = false
  end

  private

  def trap_signals
    Signal.trap("INT") do
      # Ctrl+C: 
      puts
      puts "Interrupted."
      show_cursor
      exit 130
    end
  end

  def now
    Process.clock_gettime(Process::CLOCK_MONOTONIC)
  end

  def color_for(progress)
    case progress
    when 0...0.33 then 31 # red
    when 0.33...0.66 then 33 # yellow
    else 32 # green
    end
  end

  def ansi(code)
    "\e[#{code}m"
  end

  def reset
    "\e[0m"
  end

  def hide_cursor
    print "\e[?25l"
  end

  def show_cursor
    print "\e[?25h"
  end

  def clear_line
    print "\r\e[2K"
  end

  def fmt_time(seconds)
    s = seconds.round
    mm = s / 60
    ss = s % 60
    format("%02d:%02d", mm, ss)
  end

  def render(elapsed, remaining)
    progress = [[elapsed / @total.to_f, 0.0].max, 1.0].min
    filled = (progress * @bar_width).round
    empty = @bar_width - filled

    bar = ("*" * filled) + (" " * empty)

    color = color_for(progress)
    percent = (progress * 100).round

    line = +""
    line << "#{@label} "
    line << "#{fmt_time(remaining)} "
    line << "(#{fmt_time(elapsed)}/#{fmt_time(@total)}) "
    line << "#{percent.to_s.rjust(3)}% "
    line << "#{ansi(color)}[#{bar}]#{reset}"

    clear_line
    print line
    $stdout.flush
  end

  def finish_message
    puts
    puts "\e[7m DONE! #{@label} finished. \e[0m"
  end
end

# --- parsing ---

def parse_duration(arg)
  s = arg.to_s.strip
  raise ArgumentError, "duration is required" if s.empty?

  # mm:ss
  if s.match?(/^\d{1,3}:\d{2}$/)
    mm, ss = s.split(":").map(&:to_i)
    return (mm * 60) + ss
  end

  # plain integer -> seconds
  if s.match?(/^\d+$/)
    return s.to_i
  end

  # like 1m30s / 90s / 25m / 1h2m3s
  # allow optional h/m/s in any order but typical order
  m = s.match(/\A(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?\z/i)
  if m
    hh = (m[1] || "0").to_i
    mm = (m[2] || "0").to_i
    ss = (m[3] || "0").to_i
    total = hh * 3600 + mm * 60 + ss
    return total if total > 0
  end

  raise ArgumentError, "invalid duration: #{arg.inspect} (examples: 25m, 90s, 1m30s, 25:00, 1500)"
end

def parse_args(argv)
  if argv.empty?
    puts "Usage: ruby pomotimer.rb DURATION [LABEL]"
    puts "  DURATION examples: 25m, 90s, 1m30s, 25:00, 1500"
    puts "  LABEL optional: e.g., 'FOCUS'"
    exit 1
  end

  duration = parse_duration(argv[0])
  label = argv[1] || "TIMER"
  [duration, label]
end

total_seconds, label = parse_args(ARGV)
timer = ConsoleTimer.new(total_seconds: total_seconds, label: label)
timer.run
