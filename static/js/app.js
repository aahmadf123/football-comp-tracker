/* ===================================================
   Players Table - Frontend Logic
   =================================================== */

let playersTable;
let playersData = [];
let positionCaps = {};

// --- Utility ---
function formatMoney(val) {
    const num = parseFloat(val) || 0;
    return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function statusBadge(s) {
    const cls = { Signed: 'bg-success', Offered: 'bg-info', Negotiating: 'bg-warning text-dark', Declined: 'bg-danger' };
    return `<span class="badge ${cls[s] || 'bg-secondary'}">${s || 'Signed'}</span>`;
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
        if (alert.parentNode) { new bootstrap.Alert(alert).close(); }
    }, 4000);
}

function updateFooterTotals() {
    if (!window.canSeeComp) return;
    let revTotal = 0, stipendTotal = 0, compTotal = 0;
    playersTable.rows({ search: 'applied' }).data().each(function (row) {
        revTotal  += parseFloat(row.rev_share) || 0;
        stipendTotal += parseFloat(row.stipend) || 0;
        compTotal += parseFloat(row.total) || 0;
    });
    $('#totalRevShare').text(formatMoney(revTotal));
    $('#totalStipend').text(formatMoney(stipendTotal));
    $('#totalComp').text(formatMoney(compTotal));
}

// URL parameter persistence
function readURLParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        position: params.get('position') || '',
        year: params.get('year') || '',
        campus: params.get('campus') || '',
        contract: params.get('contract') || '',
        status: params.get('status') || '',
        search: params.get('search') || '',
    };
}

function writeURLParams() {
    const params = new URLSearchParams();
    const pos = $('#filterPosition').val();
    const yr = $('#filterYear').val();
    const campus = $('#filterCampus').val();
    const contract = $('#filterContract').val();
    const status = $('#filterStatus').val();
    const search = playersTable ? playersTable.search() : '';
    if (pos) params.set('position', pos);
    if (yr) params.set('year', yr);
    if (campus) params.set('campus', campus);
    if (contract) params.set('contract', contract);
    if (status) params.set('status', status);
    if (search) params.set('search', search);
    const qs = params.toString();
    history.replaceState(null, '', window.location.pathname + (qs ? '?' + qs : ''));
}

// Position cap check
function checkPositionCap(position) {
    if (!position || !positionCaps[position]) {
        $('#posCapWarning').addClass('d-none');
        return;
    }
    const max = positionCaps[position];
    if (max > 0) {
        const current = playersData.filter(p => p.position === position).length;
        if (current >= max) {
            $('#posCapMsg').text(`Position ${position} is at capacity (${current}/${max} players).`);
            $('#posCapWarning').removeClass('d-none');
            return;
        }
    }
    $('#posCapWarning').addClass('d-none');
}

// Load position caps from API
function loadPositionCaps() {
    $.get('/api/position-caps')
        .done(data => { positionCaps = data; })
        .fail(() => { positionCaps = {}; });
}

// --- Build DataTable columns based on canSeeComp ---
function buildColumns() {
    const cols = [
        { data: 'last_name' },
        { data: 'first_name', render: function(d, _, row) {
            return `<a href="/players/${row.id}/profile" class="text-decoration-none text-ut-gold-link">${d}</a>`;
        }},
        { data: 'position', render: d => d ? `<span class="badge bg-ut-blue">${d}</span>` : '-' },
        { data: 'year' },
        { data: 'on_off_campus', render: d => {
            if (d === 'On') return '<span class="badge bg-success">On</span>';
            if (d === 'Off') return '<span class="badge bg-secondary">Off</span>';
            return d || '-';
        }},
        { data: 'status', render: d => statusBadge(d) },
    ];

    if (window.canSeeComp) {
        cols.push(
            { data: 'rev_share', render: d => {
                const val = parseFloat(d) || 0;
                return `<span class="${val > 0 ? 'money-positive' : 'money-zero'}">${formatMoney(val)}</span>`;
            }},
            { data: 'contract_length', render: d => d || '-' },
            { data: 'stipend', render: d => {
                const val = parseFloat(d) || 0;
                return `<span class="${val > 0 ? 'money-positive' : 'money-zero'}">${formatMoney(val)}</span>`;
            }},
            { data: 'total', render: d => {
                const val = parseFloat(d) || 0;
                return `<strong class="${val > 0 ? 'money-positive' : 'money-zero'}">${formatMoney(val)}</strong>`;
            }},
        );
    }

    cols.push(
        { data: 'notes', render: d => {
            if (!d) return '';
            const short = d.length > 30 ? d.substring(0, 30) + '...' : d;
            return `<span title="${$('<span>').text(d).html()}">${$('<span>').text(short).html()}</span>`;
        }},
        { data: 'updated_at', render: d => `<small class="text-muted">${d || ''}</small>` },
        { data: null, orderable: false, render: function(row) {
            let html = '<div class="d-flex gap-1 justify-content-center">';
            html += `<a href="/players/${row.id}/profile" class="btn btn-sm btn-outline-info btn-action" title="Profile"><i class="bi bi-person-lines-fill"></i></a>`;
            html += `<button class="btn btn-sm btn-outline-primary btn-action edit-btn" data-id="${row.id}" title="Edit"><i class="bi bi-pencil"></i></button>`;
            html += `<button class="btn btn-sm btn-outline-danger btn-action delete-btn" data-id="${row.id}" title="Delete"><i class="bi bi-trash"></i></button>`;
            html += '</div>';
            return html;
        }},
    );
    return cols;
}

// --- Init DataTable ---
$(document).ready(function () {
    loadPositionCaps();

    const urlParams = readURLParams();

    playersTable = $('#playersTable').DataTable({
        ajax: {
            url: '/api/players',
            dataSrc: function (json) { playersData = json; return json; }
        },
        columns: buildColumns(),
        order: [[0, 'asc']],
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']],
        language: {
            search: '<i class="bi bi-search"></i>',
            searchPlaceholder: 'Search players...',
            emptyTable: 'No players found. Add a player or upload a CSV to get started.',
            zeroRecords: 'No matching players found.',
        },
        drawCallback: function () {
            updateFooterTotals();
            writeURLParams();
        },
        responsive: true,
        rowGroup: {
            enable: false,
            dataSrc: 'position',
            startRender: function (rows, group) {
                const posLabel = group || 'Unknown';
                const count = rows.count();
                let revTotal = 0, stipendTotal = 0, compTotal = 0;
                rows.data().each(row => {
                    revTotal    += parseFloat(row.rev_share) || 0;
                    stipendTotal += parseFloat(row.stipend) || 0;
                    compTotal   += parseFloat(row.total) || 0;
                });
                const colSpanLeft = window.canSeeComp ? 3 : 3;
                let tr = $('<tr class="table-secondary fw-semibold"/>');
                if (window.canSeeComp) {
                    tr.append(`<td colspan="3"><span class="badge bg-ut-blue me-2">${posLabel}</span>${count} player${count !== 1 ? 's' : ''}</td>`)
                      .append('<td colspan="2"></td>')
                      .append(`<td>${formatMoney(revTotal)}</td>`)
                      .append('<td></td>')
                      .append(`<td>${formatMoney(stipendTotal)}</td>`)
                      .append(`<td>${formatMoney(compTotal)}</td>`)
                      .append('<td colspan="3"></td>');
                } else {
                    tr.append(`<td colspan="6"><span class="badge bg-ut-blue me-2">${posLabel}</span>${count} player${count !== 1 ? 's' : ''}</td>`)
                      .append('<td colspan="3"></td>');
                }
                return tr;
            },
        },
    });

    // Apply URL params after table loads
    playersTable.one('init', function () {
        const cols = window.canSeeComp
            ? { position: 2, year: 3, campus: 4, status: 5, contract: 7 }
            : { position: 2, year: 3, campus: 4, status: 5 };

        if (urlParams.position) { $('#filterPosition').val(urlParams.position); playersTable.column(cols.position).search(urlParams.position); }
        if (urlParams.year)     { $('#filterYear').val(urlParams.year);          playersTable.column(cols.year).search(urlParams.year); }
        if (urlParams.campus)   { $('#filterCampus').val(urlParams.campus);      playersTable.column(cols.campus).search(urlParams.campus); }
        if (urlParams.status)   { $('#filterStatus').val(urlParams.status);      playersTable.column(cols.status).search(urlParams.status); }
        if (urlParams.contract && window.canSeeComp) { $('#filterContract').val(urlParams.contract); playersTable.column(cols.contract).search(urlParams.contract); }
        if (urlParams.search)   { playersTable.search(urlParams.search); }
        if (Object.values(urlParams).some(v => v)) playersTable.draw();
    });

    // --- Group by Position Toggle ---
    let groupByEnabled = false;
    $('#toggleGroupBy').on('click', function () {
        groupByEnabled = !groupByEnabled;
        if (groupByEnabled) {
            playersTable.rowGroup().enable();
            playersTable.order([2, 'asc']).draw();
            $(this).removeClass('btn-outline-primary').addClass('btn-primary');
        } else {
            playersTable.rowGroup().disable();
            playersTable.order([0, 'asc']).draw();
            $(this).removeClass('btn-primary').addClass('btn-outline-primary');
        }
    });

    // --- Column Filters ---
    const colIdx = window.canSeeComp
        ? { position: 2, year: 3, campus: 4, status: 5, contract: 7 }
        : { position: 2, year: 3, campus: 4, status: 5 };

    $('#filterPosition').on('change', function () { playersTable.column(colIdx.position).search(this.value).draw(); });
    $('#filterYear').on('change',     function () { playersTable.column(colIdx.year).search(this.value).draw(); });
    $('#filterCampus').on('change',   function () { playersTable.column(colIdx.campus).search(this.value).draw(); });
    $('#filterStatus').on('change',   function () { playersTable.column(colIdx.status).search(this.value).draw(); });
    if (window.canSeeComp) {
        $('#filterContract').on('change', function () { playersTable.column(colIdx.contract).search(this.value).draw(); });
    }

    $('#clearFilters').on('click', function () {
        $('#filterPosition, #filterYear, #filterCampus, #filterContract, #filterStatus').val('');
        playersTable.columns().search('').search('').draw();
        writeURLParams();
    });

    // Position cap warning on position select in add modal
    $('[name="position"]', '#addPlayerForm').on('change', function () {
        checkPositionCap(this.value);
    });

    // --- Add Player ---
    $('#saveNewPlayer').on('click', function () {
        const form = $('#addPlayerForm')[0];
        if (!form.checkValidity()) { form.reportValidity(); return; }

        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Saving...');

        const data = {
            first_name: $('[name="first_name"]', '#addPlayerForm').val(),
            last_name:  $('[name="last_name"]',  '#addPlayerForm').val(),
            position:   $('[name="position"]',   '#addPlayerForm').val(),
            year:       $('[name="year"]',       '#addPlayerForm').val(),
            on_off_campus:    $('[name="on_off_campus"]',    '#addPlayerForm').val(),
            contract_length:  $('[name="contract_length"]',  '#addPlayerForm').val(),
            contract_start_date: $('[name="contract_start_date"]', '#addPlayerForm').val(),
            status: $('[name="status"]', '#addPlayerForm').val(),
            notes:  $('[name="notes"]',  '#addPlayerForm').val(),
        };
        if (window.canSeeComp) {
            data.rev_share = parseFloat($('[name="rev_share"]', '#addPlayerForm').val()) || 0;
            data.stipend   = parseFloat($('[name="stipend"]',   '#addPlayerForm').val()) || 0;
        } else {
            data.rev_share = 0; data.stipend = 0;
        }

        $.ajax({
            url: '/api/players', method: 'POST',
            contentType: 'application/json', data: JSON.stringify(data),
            success: function () {
                $('#addPlayerModal').modal('hide');
                form.reset();
                $('#posCapWarning').addClass('d-none');
                playersTable.ajax.reload();
                showToast('Player added successfully!', 'success');
            },
            error: function (xhr) {
                showToast(xhr.responseJSON ? xhr.responseJSON.error : 'Failed to add player.', 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-check-lg me-1"></i>Add Player');
            },
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
        $('#editContract').val(player.contract_length);
        $('#editContractStart').val(player.contract_start_date || '');
        $('#editStatus').val(player.status || 'Signed');
        $('#editNotes').val(player.notes);
        if (window.canSeeComp) {
            $('#editRevShare').val(player.rev_share);
            $('#editStipend').val(player.stipend);
        }
        $('#editPlayerModal').modal('show');
    });

    $('#saveEditPlayer').on('click', function () {
        const form = $('#editPlayerForm')[0];
        if (!form.checkValidity()) { form.reportValidity(); return; }

        const id  = $('#editPlayerId').val();
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Saving...');

        const data = {
            first_name:    $('#editFirstName').val(),
            last_name:     $('#editLastName').val(),
            position:      $('#editPosition').val(),
            year:          $('#editYear').val(),
            on_off_campus: $('#editCampus').val(),
            contract_length:     $('#editContract').val(),
            contract_start_date: $('#editContractStart').val(),
            status: $('#editStatus').val(),
            notes:  $('#editNotes').val(),
        };
        if (window.canSeeComp) {
            data.rev_share = parseFloat($('#editRevShare').val()) || 0;
            data.stipend   = parseFloat($('#editStipend').val())  || 0;
        }

        $.ajax({
            url: '/api/players/' + id, method: 'PUT',
            contentType: 'application/json', data: JSON.stringify(data),
            success: function () {
                $('#editPlayerModal').modal('hide');
                playersTable.ajax.reload();
                showToast('Player updated successfully!', 'success');
            },
            error: function (xhr) {
                showToast(xhr.responseJSON ? xhr.responseJSON.error : 'Failed to update player.', 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-check-lg me-1"></i>Save Changes');
            },
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
        const id  = $('#deletePlayerId').val();
        const btn = $(this);
        btn.prop('disabled', true).html('<i class="bi bi-hourglass-split me-1"></i>Deleting...');

        $.ajax({
            url: '/api/players/' + id, method: 'DELETE',
            success: function () {
                $('#deletePlayerModal').modal('hide');
                playersTable.ajax.reload();
                showToast('Player deleted successfully.', 'success');
            },
            error: function (xhr) {
                showToast(xhr.responseJSON ? xhr.responseJSON.error : 'Failed to delete player.', 'danger');
            },
            complete: function () {
                btn.prop('disabled', false).html('<i class="bi bi-trash me-1"></i>Delete Player');
            },
        });
    });
});
