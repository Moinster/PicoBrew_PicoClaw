Highcharts.setOptions({
    time: {
        useUTC: false
    }
});

function initiatizeChart(graph_data) {
  Highcharts.chart(graph_data.chart_id, {
    chart: {
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

    xAxis: {
      type: 'datetime',
      dateTimeLabelFormats: {
        day: '%b %e'
      },
      title: {
        text: 'Time'
      },
    },

    yAxis: [
      {
        title: {
          text: 'Temperature (F)'
        },
        //min: 50
        //max: 90
      }, {
        title: {
          text: 'Pressure (psi)'
        },
        min: 0,
        //max: 15
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
}
