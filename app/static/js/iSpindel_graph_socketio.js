Highcharts.setOptions({
  time: {
    useUTC: false
  }
});

Highcharts.chart(graph_data.chart_id, {
  chart: {
    events: {
      load: function () {
        var self = this
        var event_name = 'iSpindel_session_update|' + graph_data.chart_id
        socket.on(event_name, function (event) {
          var data = JSON.parse(event);
          self.setTitle(graph_data.title, { text: data.subtitle });
          for (point of data['data']) {
            self.series[0].addPoint([point.time, point.temp]);
            self.series[1].addPoint([point.time, point.gravity]);
          }
        });
      },
    },

    type: 'spline',
    zoomType: 'xy',
    panning: {
      enabled: true,
      type: 'xy'
    },
    panKey: 'shift',
    pinchType: 'xy'
  },

  credits: {
    enabled: false
  },

  colors: ['#F93', '#9F3', '#06C', '#036', '#000'],

  plotOptions: {
    spline: {
      marker: {
        enabled: true,
        radius: 3
      }
    },
    series: {
      states: {
        inactive: {
          opacity: 1
        }
      }
    }
  },

  legend: {
    itemStyle: {
      fontSize: '12px'
    },
    itemMarginBottom: 5
  },

  title: graph_data.title,

  subtitle: graph_data.subtitle,

  tooltip: {
    formatter: function () {
      var s = '<b>' + Highcharts.dateFormat('%A, %b %e %k:%M:%S.%L', // Friday, Jan ## ##:##:##.####
        new Date(this.x)) + '</b>';

      $.each(this.points, function (i, point) {
        s += '<br/><span style="color:' + point.color + '">\u25CF</span> ' + point.series.name + ': ' + point.y;
      });

      return s;
    },
    shared: true
  },

  xAxis: {
    type: 'datetime',
    dateTimeLabelFormats: {
      day: '%b %e'
    },
    title: {
      text: 'Time'
    },
  },

  yAxis: [{
    title: {
      text: 'Temperature (F)'
    },

    labels: {
      format: '{value:,.0f}'
    },

    tickPositioner: function () {
      var positions = [],
        incrementNum = 6,
        tick = this.dataMin,
        increment = (this.dataMax - this.dataMin) / incrementNum;

      if (this.dataMax !== null && this.dataMin !== null) {
        for (let i = 0; i <= incrementNum; i++) {
          positions.push(tick),
            tick += increment;
        }
      }
      TickAmountValue = positions.length;
      return positions;
    },
  }, {
    title: {
      text: 'Specific Gravity'
    },

    labels: {
      format: '{value:,.3f}'
    },

    tickPositioner: function () {
      var positions = [],
        incrementNum = TickAmountValue - 1,
        maxTick = this.dataMax,
        tick = this.dataMin,
        increment = (maxTick - this.dataMin) / incrementNum;

      if (this.dataMax !== null && this.dataMin !== null) {
        for (let i = 0; i <= incrementNum; i++) {
          positions.push(tick),
            tick += increment;
        }
      }
      return positions;
    },

    opposite: true
  }],

  series: graph_data.series,

  responsive: {
    rules: [{
      condition: {
        maxWidth: 600
      },
      chartOptions: {
        chart: {
          spacingLeft: 5,
          spacingRight: 5
        },
        legend: {
          layout: 'horizontal',
          align: 'center',
          verticalAlign: 'bottom',
          itemStyle: {
            fontSize: '10px'
          }
        },
        xAxis: {
          title: {
            text: null
          },
          labels: {
            style: {
              fontSize: '10px'
            }
          }
        },
        yAxis: [{
          title: {
            text: null
          },
          labels: {
            style: {
              fontSize: '10px'
            }
          }
        }, {
          title: {
            text: null
          },
          labels: {
            style: {
              fontSize: '10px'
            }
          }
        }],
        plotOptions: {
          spline: {
            marker: {
              radius: 2
            }
          }
        }
      }
    }]
  }
});
