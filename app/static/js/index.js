function showAlert(msg, type) {
    $('#alert').html("<div class='w-75 alert text-center alert-" + type + "'>" + msg + "</div>");
    $('#alert').show();
}

function start_monitoring(session_type, uid) {
    var session = {}
    session.active = true
    $.ajax({
        url: `/device/${uid}/sessions/${session_type}`,
        type: 'PUT',
        data: JSON.stringify(session),
        dataType: "json",
        processData: false,
        contentType: "application/json; charset=UTF-8",
        success: function (data) {
            showAlert("Success!", "success");

            $("#bstart_" + uid).toggleClass('d-block d-none')
            $("#bstop_" + uid).toggleClass('d-block d-none')
            $("#ferm_status_panel_" + uid).show();
            // setTimeout(function () { window.location.href = "/"; }, 2000);
        },
        error: function (request, status, error) {
            showAlert("Error: " + request.responseText, "danger");
            window.scrollTo({top: 0, behavior: 'smooth'});
            //setTimeout(function () { window.location.href = "pico_recipes";}, 2000);
        },
    });
}

function stop_monitoring(session_type, uid) {
    var session = {}
    session.active = false
    $.ajax({
        url: `/device/${uid}/sessions/${session_type}`,
        type: 'PUT',
        data: JSON.stringify(session),
        dataType: "json",
        processData: false,
        contentType: "application/json; charset=UTF-8",
        success: function (data) {
            showAlert("Success!", "success");
            $("#bstart_" + uid).toggleClass('d-block d-none')
            $("#bstop_" + uid).toggleClass('d-block d-none')

            // until socketio publishes a new "empty" state just force a refresh (which will clear the graphs)
            setTimeout(function () { window.location.href = "/"; }, 2000);
        },
        error: function (request, status, error) {
            showAlert("Error: " + request.responseText, "danger");
            window.scrollTo({top: 0, behavior: 'smooth'});
            //setTimeout(function () { window.location.href = "pico_recipes";}, 2000);
        },
    });
}

// -------- Fermentation with ABV/Pressure Settings --------

// Fermentation time lookup tables (days) - matches server-side calculator
const FERM_TIMES = {
    low: { hot: [4, 5], warm: [5, 6], cool: [6, 7], cold: [7, 9] },      // ABV <= 6.5%
    medium: { hot: [6, 8], warm: [7, 9], cool: [9, 12], cold: [12, 14] }, // 6.5% < ABV <= 8.5%
    high: { hot: [9, 10], warm: [10, 12], cool: [12, 14], cold: [14, 18] } // ABV > 8.5%
};

function getAbvCategory(abv) {
    if (abv <= 6.5) return 'low';
    if (abv <= 8.5) return 'medium';
    return 'high';
}

function getTempCategory(tempF) {
    if (tempF >= 75) return 'hot';
    if (tempF >= 70) return 'warm';
    if (tempF >= 65) return 'cool';
    return 'cold';
}

function calculatePressureFactor(psi) {
    const basePsi = 5.0;
    const adjustmentPerPsi = 0.04;
    let factor = 1.0 + ((psi - basePsi) * adjustmentPerPsi);
    return Math.max(0.7, Math.min(2.0, factor));
}

function estimateFermDays(abv, tempF, psi) {
    const abvCat = getAbvCategory(abv);
    const tempCat = getTempCategory(tempF || 70); // Default to 70°F if not specified
    const [minDays, maxDays] = FERM_TIMES[abvCat][tempCat];
    const pressureFactor = calculatePressureFactor(psi || 5);
    return [minDays * pressureFactor, maxDays * pressureFactor];
}

function updateFermTimeEstimate() {
    const abv = parseFloat($('#ferm_target_abv').val()) || 5.0;
    const psi = parseFloat($('#ferm_target_pressure').val()) || 5;
    const conservative = $('#ferm_conservative').is(':checked');
    
    // Estimate at 70°F (common fermentation temp)
    const [minDays, maxDays] = estimateFermDays(abv, 70, psi);
    
    let estimate = '';
    if (conservative) {
        estimate = `${minDays.toFixed(1)} - ${maxDays.toFixed(1)} days (at 70°F)`;
    } else {
        estimate = `${minDays.toFixed(1)} - ${maxDays.toFixed(1)} days (at 70°F)`;
    }
    
    // Add pressure note if not at baseline
    if (psi !== 5) {
        if (psi > 5) {
            estimate += ` <small class="text-warning">(+${Math.round((psi - 5) * 4)}% for higher pressure)</small>`;
        } else {
            estimate += ` <small class="text-success">(-${Math.round((5 - psi) * 4)}% for lower pressure)</small>`;
        }
    }
    
    $('#ferm_time_estimate').html(estimate);
}

function showFermStartModal(uid) {
    $('#ferm_modal_uid').val(uid);
    updateFermTimeEstimate();
    $('#fermStartModal').modal('show');
}

function startFermentationWithParams() {
    const uid = $('#ferm_modal_uid').val();
    const targetAbv = parseFloat($('#ferm_target_abv').val());
    const targetPressure = parseFloat($('#ferm_target_pressure').val());
    const autoComplete = $('#ferm_auto_complete').is(':checked');
    const useConservative = $('#ferm_conservative').is(':checked');
    
    // First set the fermentation parameters
    $.ajax({
        url: '/API/PicoFerm/setFermentationParams',
        type: 'POST',
        data: JSON.stringify({
            uid: uid,
            target_abv: targetAbv,
            target_pressure_psi: targetPressure,
            auto_complete: autoComplete,
            use_conservative: useConservative
        }),
        contentType: "application/json; charset=UTF-8",
        success: function(data) {
            // Update the target ABV display
            $('#target_abv_' + uid).text(targetAbv + '%');
            
            // Now start the monitoring
            start_monitoring('ferm', uid);
            
            // Close the modal
            $('#fermStartModal').modal('hide');
        },
        error: function(request, status, error) {
            showAlert("Error setting fermentation parameters: " + request.responseText, "danger");
        }
    });
}

// Update fermentation status UI from socketio data
function updateFermStatusUI(uid, status) {
    if (!status || !status.can_estimate) {
        $('#ferm_est_completion_' + uid).text('Waiting for data...');
        $('#ferm_est_days_' + uid).text('--');
        $('#ferm_recommendation_' + uid).text(status?.recommendation || 'Waiting for data...');
        return;
    }
    
    // Update progress bar
    const progress = status.progress_percent || 0;
    const progressBar = $('#ferm_progress_' + uid);
    progressBar.css('width', progress + '%');
    progressBar.attr('aria-valuenow', progress);
    progressBar.text(Math.round(progress) + '%');
    
    // Change color based on progress
    progressBar.removeClass('bg-success bg-warning bg-info');
    if (progress >= 100) {
        progressBar.addClass('bg-success');
    } else if (progress >= 75) {
        progressBar.addClass('bg-warning');
    } else {
        progressBar.addClass('bg-info');
    }
    
    // Update estimated completion
    if (status.estimated_completion) {
        const estDate = new Date(status.estimated_completion);
        $('#ferm_est_completion_' + uid).text(estDate.toLocaleDateString() + ' ' + estDate.toLocaleTimeString());
    }
    
    // Update estimated days
    if (status.estimated_min_days && status.estimated_max_days) {
        $('#ferm_est_days_' + uid).text(status.estimated_min_days + ' - ' + status.estimated_max_days + ' days');
    }
    
    // Update recommendation
    if (status.recommendation) {
        $('#ferm_recommendation_' + uid).text(status.recommendation);
    }
    
    // If should complete, highlight the panel
    if (status.should_complete) {
        $('#ferm_status_panel_' + uid).find('.card').removeClass('bg-secondary').addClass('bg-success');
    }
}

// Handle fermentation auto-complete event
function handleFermAutoComplete(uid, data) {
    console.log('Fermentation auto-complete:', uid, data);
    
    // Update the UI immediately - toggle buttons
    $("#bstart_" + uid).removeClass('d-none').addClass('d-block');
    $("#bstop_" + uid).removeClass('d-block').addClass('d-none');
    
    // Update the status panel to show completion
    const statusPanel = $('#ferm_status_panel_' + uid);
    statusPanel.find('.card').removeClass('bg-secondary bg-warning bg-info').addClass('bg-success');
    
    // Update progress to 100%
    const progressBar = $('#ferm_progress_' + uid);
    progressBar.css('width', '100%');
    progressBar.attr('aria-valuenow', 100);
    progressBar.text('100%');
    progressBar.removeClass('bg-warning bg-info').addClass('bg-success');
    
    // Update recommendation text
    $('#ferm_recommendation_' + uid).html('<i class="fas fa-check-circle"></i> Fermentation Complete!');
    
    // Get status details for the modal
    const status = data.status || {};
    const analysis = status.analysis || {};
    
    // Format the completion details
    let detailsHtml = '<ul class="list-unstyled mb-0">';
    if (status.target_abv) {
        detailsHtml += '<li><strong>Target ABV:</strong> ' + status.target_abv + '%</li>';
    }
    if (analysis.avg_temp) {
        detailsHtml += '<li><strong>Avg Temperature:</strong> ' + analysis.avg_temp.toFixed(1) + '°F</li>';
    }
    if (analysis.avg_pressure) {
        detailsHtml += '<li><strong>Avg Pressure:</strong> ' + analysis.avg_pressure.toFixed(1) + ' PSI</li>';
    }
    if (status.estimated_min_days && status.estimated_max_days) {
        detailsHtml += '<li><strong>Estimated Duration:</strong> ' + status.estimated_min_days + ' - ' + status.estimated_max_days + ' days</li>';
    }
    if (analysis.data_points) {
        detailsHtml += '<li><strong>Data Points:</strong> ' + analysis.data_points + '</li>';
    }
    detailsHtml += '</ul>';
    
    // Show the completion modal
    $('#fermCompleteModalLabel').html('<i class="fas fa-check-circle text-success"></i> Fermentation Complete!');
    $('#fermCompleteUid').text(uid);
    $('#fermCompleteReason').text(data.reason || 'Estimated fermentation time reached');
    $('#fermCompleteDetails').html(detailsHtml);
    $('#fermCompleteModal').modal('show');
    
    // Also show an alert
    showAlert('🎉 Fermentation complete for ' + uid + '! ' + (data.reason || ''), 'success');
}

// Listen for input changes on the modal
$(document).ready(function() {
    $('#ferm_target_abv, #ferm_target_pressure, #ferm_conservative').on('change input', function() {
        updateFermTimeEstimate();
    });
});