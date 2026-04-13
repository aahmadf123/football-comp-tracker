/* ===================================================
   Players Table - Frontend Logic
   =================================================== */

let playersTable;
let playersData = [];

// --- Utility ---
function formatMoney(val) {
    const num = parseFloat(val) || 0;
    return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showToast(message, type) {
    const container = document.querySelector('.container-fluid.mt-3') || document.querySelector('main');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    const icon = type === 'success' ? 'check-circle-fill' : type === 'danger' ? 'exclamation-triangle-fill' : 'info-circle-fill';
    alert.innerHTML = `<i class="bi bi-${icon} me-2"></i>${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    container.prepend(alert);
    setTimeout(() => {
        if (alert.parentNode) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }
    }, 4000);
}

function updateFooterTotals() {
    let revTotal = 0, stipendTotal = 0, compTotal = 0;

    // Sum only visible (filtered) rows
    playersTable.rows({ search: 'applied' }).data().each(function(row) {
        revTotal += parseFloat(row.rev_share) || 0;
        stipendTotal += parseFloat(row.stipend) || 0;
        compTotal += parseFloat(row.total) || 0;
    });

    $('#totalRevShare').text(formatMoney(revTotal));
    $('#totalStipend').text(formatMoney(stipendTotal));
    $('#totalComp').text(formatMoney(compTotal));
}

// --- Init DataTable ---
$(document).ready(function () {
    playersTable = $('#playersTable').DataTable({
        ajax: {
            url: '/api/players',
            dataSrc: function (json) {
                playersData = json;
                return json;
            }
        },
        columns: [
            { data: 'last_name' },
            { data: 'first_name' },
            { data: 'position', render: function(d) { return d ? '<span class="badge bg-ut-blue">' + d + '</span>' : '-'; }},
            { data: 'year' },
            { data: 'on_off_campus', render: function(d) {
                if (d === 'On') return '<span class="badge bg-success">On</span>';
                if (d === 'Off') return '<span class="badge bg-secondary">Off</span>';
                return d || '-';
            }},
            { data: 'rev_share', render: function(d) {
                const val = parseFloat(d) || 0;
                return '<span class="' + (val > 0 ? 'money-positive' : 'money-zero') + '">' + formatMoney(val) + '</span>';
            }},
            { data: 'contract_length', render: function(d) { return d || '-'; }},
            { data: 'stipend', render: function(d) {
                const val = parseFloat(d) || 0;
                return '<span class="' + (val > 0 ? 'money-positive' : 'money-zero') + '">' + formatMoney(val) + '</span>';
            }},
            { data: 'total', render: function(d) {
                const val = parseFloat(d) || 0;
                return '<strong class="' + (val > 0 ? 'money-positive' : 'money-zero') + '">' + formatMoney(val) + '</strong>';
            }},
            { data: 'notes', render: function(d) {
                if (!d) return '';
                const short = d.length > 30 ? d.substring(0, 30) + '...' : d;
                return '<span title="' + $('<span>').text(d).html() + '">' + $('<span>').text(short).html() + '</span>';
            }},
            { data: 'updated_at', render: function(d) {
                return '<small class="text-muted">' + (d || '') + '</small>';
            }},
            { data: null, orderable: false, render: function(data) {
                let html = '<div class="d-flex gap-1 justify-content-center">';
                html += '<button class="btn btn-sm btn-outline-primary btn-action edit-btn" data-id="' + data.id + '" title="Edit">';
                html += '<i class="bi bi-pencil"></i></button>';
                html += '<button class="btn btn-sm btn-outline-danger btn-action delete-btn" data-id="' + data.id + '" title="Delete">';
                html += '<i class="bi bi-trash"></i></button>';
                html += '</div>';
                return html;
            }}
        ],
        order: [[0, 'asc']],
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
        language: {
            search: '<i class="bi bi-search"></i>',
            searchPlaceholder: 'Search players...',
            emptyTable: 'No players found. Add a player or upload a CSV to get started.',
            zeroRecords: 'No matching players found.',
        },
        drawCallback: function() {
            updateFooterTotals();
        },
        responsive: true,
    });

    // --- Column Filters ---
    $('#filterPosition').on('change', function () {
        playersTable.column(2).search(this.value).draw();
    });
    $('#filterYear').on('change', function () {
        playersTable.column(3).search(this.value).draw();
    });
    $('#filterCampus').on('change', function () {
        playersTable.column(4).search(this.value).draw();
    });
    $('#filterContract').on('change', function () {
        playersTable.column(6).search(this.value).draw();
    });
    $('#clearFilters').on('click', function () {
        $('#filterPosition, #filterYear, #filterCampus, #filterContract').val('');
        playersTable.columns().search('').draw();
    });

    // --- Add Player ---
    $('#saveNewPlayer').on('click', function () {
        const form = $('#addPlayerForm')[0];
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Saving...');

        const data = {
            first_name: $('[name="first_name"]', '#addPlayerForm').val(),
            last_name: $('[name="last_name"]', '#addPlayerForm').val(),
            position: $('[name="position"]', '#addPlayerForm').val(),
            year: $('[name="year"]', '#addPlayerForm').val(),
            on_off_campus: $('[name="on_off_campus"]', '#addPlayerForm').val(),
            rev_share: parseFloat($('[name="rev_share"]', '#addPlayerForm').val()) || 0,
            contract_length: $('[name="contract_length"]', '#addPlayerForm').val(),
            stipend: parseFloat($('[name="stipend"]', '#addPlayerForm').val()) || 0,
            notes: $('[name="notes"]', '#addPlayerForm').val(),
        };

        $.ajax({
            url: '/api/players',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function () {
                $('#addPlayerModal').modal('hide');
                form.reset();
                playersTable.ajax.reload();
                showToast('Player added successfully!', 'success');
            },
            error: function (xhr) {
                const msg = xhr.responseJSON ? xhr.responseJSON.error : 'Failed to add player.';
                showToast(msg, 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-check-lg me-1"></i>Add Player');
            }
        });
    });

    // --- Edit Player ---
    $(document).on('click', '.edit-btn', function () {
        const id = $(this).data('id');
        const player = playersData.find(p => p.id === id);
        if (!player) return;

        $('#editPlayerId').val(player.id);
        $('#editFirstName').val(player.first_name);
        $('#editLastName').val(player.last_name);
        $('#editPosition').val(player.position);
        $('#editYear').val(player.year);
        $('#editCampus').val(player.on_off_campus);
        $('#editRevShare').val(player.rev_share);
        $('#editContract').val(player.contract_length);
        $('#editStipend').val(player.stipend);
        $('#editNotes').val(player.notes);
        $('#editPlayerModal').modal('show');
    });

    $('#saveEditPlayer').on('click', function () {
        const form = $('#editPlayerForm')[0];
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const id = $('#editPlayerId').val();
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Saving...');

        const data = {
            first_name: $('#editFirstName').val(),
            last_name: $('#editLastName').val(),
            position: $('#editPosition').val(),
            year: $('#editYear').val(),
            on_off_campus: $('#editCampus').val(),
            rev_share: parseFloat($('#editRevShare').val()) || 0,
            contract_length: $('#editContract').val(),
            stipend: parseFloat($('#editStipend').val()) || 0,
            notes: $('#editNotes').val(),
        };

        $.ajax({
            url: '/api/players/' + id,
            method: 'PUT',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function () {
                $('#editPlayerModal').modal('hide');
                playersTable.ajax.reload();
                showToast('Player updated successfully!', 'success');
            },
            error: function (xhr) {
                const msg = xhr.responseJSON ? xhr.responseJSON.error : 'Failed to update player.';
                showToast(msg, 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-check-lg me-1"></i>Save Changes');
            }
        });
    });

    // --- Delete Player ---
    $(document).on('click', '.delete-btn', function () {
        const id = $(this).data('id');
        const player = playersData.find(p => p.id === id);
        if (!player) return;

        $('#deletePlayerId').val(player.id);
        $('#deletePlayerName').text(player.first_name + ' ' + player.last_name);
        $('#deletePlayerModal').modal('show');
    });

    $('#confirmDelete').on('click', function () {
        const id = $('#deletePlayerId').val();
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Deleting...');

        $.ajax({
            url: '/api/players/' + id,
            method: 'DELETE',
            success: function () {
                $('#deletePlayerModal').modal('hide');
                playersTable.ajax.reload();
                showToast('Player deleted successfully.', 'success');
            },
            error: function (xhr) {
                const msg = xhr.responseJSON ? xhr.responseJSON.error : 'Failed to delete player.';
                showToast(msg, 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-trash me-1"></i>Delete Player');
            }
        });
    });
});
